// Exact immutable FP8 engram row retrieval with a bounded direct-mapped RAM
// cache in front of O_DIRECT NVMe reads.
//
// Derived from adapter/row_store.cpp in
// https://github.com/0xSero/deepseek-v4.1-flash-4x-rtx-pro-6000
// Copyright (c) 2026 0xSero, MIT License. Modifications for the KTransformers
// dual-EPYC host (kvcache-ai/ktransformers fork, 05yuki):
//   - never abort inside the callback: failures zero the row, bump an error
//     counter, and are surfaced by the Python side after stream sync;
//   - 64 KiB read staging so one pread covers a row straddling a 4 KiB edge;
//   - stats expose cache slot count and bytes so the budget is auditable.
// ds41-multi-user extension, only behind switches, default = unchanged:
//   - row_store_open_numa(): RAM mode with a NUMA placement. The table file is
//     copied into an anonymous mapping whose pages are bound per stripe to a
//     node before they are touched (mbind on a MAP_SHARED file mapping is
//     ignored by the kernel), filled by parallel O_DIRECT reads (no page cache),
//     made read-only and mlocked. row_store_open() keeps the old code path.
//   - slot cache: DSV41_ENGRAM_CACHE_THP=0 skips madvise(MADV_HUGEPAGE) (direct-
//     mapped slots make every first miss a THP fault with direct compaction),
//     DSV41_ENGRAM_CACHE_PREFAULT=1 faults the cache in at open.
//
// No CUDA calls in the callback: suitable for cudaLaunchHostFunc graph nodes.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <thread>
#include <vector>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <linux/mempolicy.h>
#include <mutex>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace {

constexpr uint64_t kDim = 256;       // fp8 e4m3 bytes per row
constexpr uint64_t kScales = 8;      // e8m0 bytes per row (block 32)
constexpr uint64_t kRow = kDim + kScales;
constexpr uint64_t kSlotBytes = kRow + sizeof(uint64_t);
constexpr size_t kPage = 4096;
constexpr int kLockShards = 256;

struct Store {
  int fd = -1;
  uint64_t rows = 0, weight_offset = 0, scale_offset = 0, slots = 0;
  uint64_t row_lo = 0, row_hi = 0;
  uint8_t *cache = nullptr;
  uint64_t *keys = nullptr;
  uint8_t *resident = nullptr;
  size_t resident_size = 0;
  // NUMA placement of the resident copy (0 = off/legacy mapping, 1 = interleave
  // in stripes, 2 = whole table on one node), sampled page nodes, load time
  int numa_mode = 0, numa_node = -1;
  uint64_t numa_n0 = 0, numa_n1 = 0, numa_other = 0, numa_load_ns = 0;
  std::mutex locks[kLockShards];
  std::atomic<uint64_t> hits{0}, misses{0}, reads{0}, errors{0};
  // timing: whole callback and the part spent on cache misses, so the share
  // of a decode step that is engram row fetches can be read off
  std::atomic<uint64_t> calls{0}, lookup_ns{0}, miss_ns{0};
  // Misses are NVMe reads at ~170 us each and a decode call has 12 rows, so
  // issuing them one after another costs ~4 ms per call per layer (09-13
  // profile: 8-9 ms of every decode token). A small pool of I/O threads,
  // created at open, runs a call's misses concurrently; the callback thread
  // waits for the batch. Size from DSV41_ENGRAM_IO_THREADS (default 16).
  struct IoPool {
    std::vector<std::thread> threads;
    std::mutex mu;
    std::condition_variable cv, done_cv;
    std::vector<std::function<void()>> queue;
    size_t next = 0, pending = 0;
    bool stop = false;
  } io;
};

void io_worker(Store *s) {
  for (;;) {
    std::function<void()> job;
    {
      std::unique_lock<std::mutex> lk(s->io.mu);
      s->io.cv.wait(lk, [&] { return s->io.stop || s->io.next < s->io.queue.size(); });
      if (s->io.stop) return;
      job = std::move(s->io.queue[s->io.next++]);
    }
    job();
    std::lock_guard<std::mutex> lk(s->io.mu);
    if (--s->io.pending == 0) {
      s->io.queue.clear();
      s->io.next = 0;
      s->io.done_cv.notify_all();
    }
  }
}

void io_start(Store *s) {
  int n = 16;
  if (const char *e = getenv("DSV41_ENGRAM_IO_THREADS")) n = std::atoi(e);
  if (n < 1) n = 1;
  if (n > 64) n = 64;
  for (int i = 0; i < n; i++) s->io.threads.emplace_back(io_worker, s);
}

void io_stop(Store *s) {
  {
    std::lock_guard<std::mutex> lk(s->io.mu);
    s->io.stop = true;
  }
  s->io.cv.notify_all();
  for (auto &t : s->io.threads) t.join();
  s->io.threads.clear();
}

// Run all jobs on the pool and wait; only one batch is in flight per store
// (the callbacks of one stream are serialised by CUDA).
void io_run_batch(Store *s, std::vector<std::function<void()>> &jobs) {
  if (jobs.empty()) return;
  std::unique_lock<std::mutex> lk(s->io.mu);
  s->io.done_cv.wait(lk, [&] { return s->io.pending == 0; });
  s->io.queue = std::move(jobs);
  s->io.next = 0;
  s->io.pending = s->io.queue.size();
  lk.unlock();
  s->io.cv.notify_all();
  lk.lock();
  s->io.done_cv.wait(lk, [&] { return s->io.pending == 0; });
}

struct Work {
  Store *store;
  const int64_t *ids;
  uint8_t *weights, *scales;
  uint64_t count;
};

// Returns false on a short or failed read. Never exits the process.
bool read_bytes(Store *s, uint64_t offset, uint8_t *out, size_t length) {
  if (s->resident) {
    std::memcpy(out, s->resident + offset, length);
    return true;
  }
  alignas(kPage) static thread_local uint8_t page[16 * kPage];
  const uint64_t base = offset & ~uint64_t(kPage - 1);
  const size_t delta = offset - base;
  const size_t requested = ((delta + length + kPage - 1) / kPage) * kPage;
  if (requested > sizeof(page)) return false;
  ssize_t got;
  do {
    got = pread(s->fd, page, requested, base);
  } while (got < 0 && errno == EINTR);
  if (got < 0 || size_t(got) < delta + length) return false;
  std::memcpy(out, page + delta, length);
  s->reads.fetch_add(1, std::memory_order_relaxed);
  return true;
}

constexpr size_t kStripe = size_t(1) << 30;  // interleave granule: 1 GiB per node, alternating
constexpr size_t kChunk = size_t(64) << 20;  // one O_DIRECT read

int env_int(const char *name, int def, int lo, int hi) {
  const char *e = getenv(name);
  if (!e || !*e) return def;
  const int v = std::atoi(e);
  return v < lo ? lo : (v > hi ? hi : v);
}

// 0/1 switch: unset or empty -> def, "0"/"1" -> value, anything else -> -1
int env_switch(const char *name, int def) {
  const char *e = getenv(name);
  if (!e || !*e) return def;
  if (!std::strcmp(e, "0")) return 0;
  if (!std::strcmp(e, "1")) return 1;
  return -1;
}

// Fault in every page of [p, p+len) now (MADV_POPULATE_WRITE, Linux >= 5.14;
// fallback: write one zero byte per page, which keeps an empty cache empty).
void prefault(void *p, size_t len) {
  if (!madvise(p, len, MADV_POPULATE_WRITE)) return;
  auto *b = static_cast<volatile uint8_t *>(p);
  for (size_t o = 0; o < len; o += kPage) b[o] = 0;
}

// MPOL_BIND, not MPOL_INTERLEAVE/PREFERRED: those fall back to the other node
// as soon as the target node is below its low watermark (e.g. full of page
// cache) instead of reclaiming there, so the placement would again depend on
// what an earlier run left behind.
long bind_range(void *addr, size_t len, int node) {
  unsigned long mask = 1UL << node;
  return syscall(SYS_mbind, addr, len, MPOL_BIND, &mask, sizeof(mask) * 8 + 1, 0);
}

// Node of every n-th page of the resident copy (move_pages query, nodes=NULL).
void sample_nodes(Store *s) {
  const size_t npages = s->resident_size / kPage;
  const size_t step = npages > 65536 ? npages / 65536 : 1;
  std::vector<void *> pages;
  for (size_t p = 0; p < npages; p += step) pages.push_back(s->resident + p * kPage);
  std::vector<int> status(pages.size(), -1);
  if (syscall(SYS_move_pages, 0, pages.size(), pages.data(), nullptr, status.data(), 0) < 0) {
    s->numa_other = pages.size();
    return;
  }
  for (int st : status) {
    if (st == 0) s->numa_n0++;
    else if (st == 1) s->numa_n1++;
    else s->numa_other++;
  }
}

// Copy [0, size) of the file into an anonymous mapping whose pages are bound
// to their node before the first touch, so the placement does not depend on
// the calling thread's policy or on page cache left by an earlier run.
// Returns false on any error and leaves nothing mapped.
bool load_resident_numa(Store *s, const char *path, size_t size) {
  const auto t0 = std::chrono::steady_clock::now();
  const size_t len = (size + kPage - 1) & ~(kPage - 1);
  void *m = mmap(nullptr, len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (m == MAP_FAILED) {
    std::fprintf(stderr, "row_store_open_numa: mmap %zu failed errno=%d (%s)\n", len, errno, path);
    return false;
  }
  auto *base = static_cast<uint8_t *>(m);
  auto fail = [&](const char *what, int err) {
    std::fprintf(stderr, "row_store_open_numa: %s failed errno=%d (%s)\n", what, err, path);
    munmap(m, len);
    return false;
  };
  if (s->numa_mode == 2) {
    if (bind_range(base, len, s->numa_node)) return fail("mbind", errno);
  } else {
    for (size_t off = 0, k = 0; off < len; off += kStripe, ++k)
      if (bind_range(base + off, std::min(kStripe, len - off), int((k + size_t(s->numa_node)) % 2)))
        return fail("mbind", errno);
  }
  const int dfd = open(path, O_RDONLY | O_CLOEXEC | O_DIRECT);
  if (dfd < 0) return fail("open(O_DIRECT)", errno);
  const size_t chunks = (len + kChunk - 1) / kChunk;
  std::atomic<size_t> next{0};
  std::atomic<int> err{0};
  auto worker = [&] {
    for (;;) {
      const size_t c = next.fetch_add(1);
      if (c >= chunks || err.load()) return;
      const size_t off = c * kChunk;
      const size_t want = std::min(kChunk, len - off);   // page multiple
      const size_t expect = std::min(want, size - off);  // bytes before EOF
      size_t done = 0;
      while (done < expect) {
        const ssize_t got = pread(dfd, base + off + done, want - done, off_t(off + done));
        if (got < 0 && errno == EINTR) continue;
        if (got < 0) {
          err.store(errno ? errno : EIO);
          return;
        }
        if (got == 0) break;
        done += size_t(got);
      }
      if (done < expect) {
        err.store(EIO);
        return;
      }
    }
  };
  const int n = env_int("DSV41_ENGRAM_RAM_THREADS", 8, 1, 32);
  std::vector<std::thread> threads;
  for (int i = 0; i < n; ++i) threads.emplace_back(worker);
  for (auto &t : threads) t.join();
  close(dfd);
  if (err.load()) return fail("O_DIRECT read", err.load());
  if (mprotect(base, len, PROT_READ)) return fail("mprotect", errno);
  if (mlock(base, len)) return fail("mlock (need RLIMIT_MEMLOCK)", errno);
  s->resident = base;
  s->resident_size = len;
  // The copy is private: drop clean, unmapped page-cache pages of the
  // read-only file that an earlier run may have left on some node.
  posix_fadvise(s->fd, 0, 0, POSIX_FADV_DONTNEED);
  s->numa_load_ns = uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count());
  sample_nodes(s);
  const double secs = s->numa_load_ns / 1e9;
  std::fprintf(stderr,
               "[engram-numa] file=%s mode=%s node=%d bytes=%zu threads=%d load_s=%.1f gib_s=%.2f "
               "sample=%llu n0=%llu n1=%llu other=%llu\n",
               path, s->numa_mode == 2 ? "split" : "interleave", s->numa_node, len, n, secs,
               secs > 0 ? len / secs / double(1ULL << 30) : 0.0,
               (unsigned long long)(s->numa_n0 + s->numa_n1 + s->numa_other), (unsigned long long)s->numa_n0,
               (unsigned long long)s->numa_n1, (unsigned long long)s->numa_other);
  return true;
}

}  // namespace

// numa_mode: 0 = legacy (MAP_SHARED|MAP_POPULATE file mapping, exactly as
// row_store_open), 1 = interleave in 1 GiB stripes starting at numa_node,
// 2 = whole table bound to numa_node. 1 and 2 need resident_mode.
extern "C" Store *row_store_open_numa(const char *path, uint64_t rows, uint64_t woff, uint64_t soff,
                                      uint64_t budget, int resident_mode, int numa_mode, int numa_node) {
  if (numa_mode < 0 || numa_mode > 2 || (numa_mode && (!resident_mode || numa_node < 0 || numa_node > 1))) {
    std::fprintf(stderr, "row_store_open_numa: invalid numa_mode=%d node=%d resident=%d\n", numa_mode, numa_node,
                 resident_mode);
    return nullptr;
  }
  // Slot cache (nvme mode): DSV41_ENGRAM_CACHE_THP=1 (default, madvise
  // MADV_HUGEPAGE as before) | 0 (no madvise: with THP "madvise" no huge pages,
  // so no direct compaction on the first misses); DSV41_ENGRAM_CACHE_PREFAULT=
  // 0 (default) | 1 (fault the cache and key pages in at open).
  const int cache_thp = env_switch("DSV41_ENGRAM_CACHE_THP", 1);
  const int cache_prefault = env_switch("DSV41_ENGRAM_CACHE_PREFAULT", 0);
  if (cache_thp < 0 || cache_prefault < 0) {
    std::fprintf(stderr, "row_store_open: DSV41_ENGRAM_CACHE_THP and DSV41_ENGRAM_CACHE_PREFAULT take 0 or 1\n");
    return nullptr;
  }
  auto *s = new Store;
  s->numa_mode = numa_mode;
  s->numa_node = numa_mode ? numa_node : -1;
  s->fd = open(path, O_RDONLY | O_CLOEXEC | (resident_mode ? 0 : O_DIRECT));
  if (s->fd < 0) {
    std::fprintf(stderr, "row_store_open: open(%s) failed errno=%d\n", path, errno);
    delete s;
    return nullptr;
  }
  struct stat st;
  if (fstat(s->fd, &st) || woff > uint64_t(st.st_size) || soff > uint64_t(st.st_size) ||
      rows > (uint64_t(st.st_size) - woff) / kDim || rows > (uint64_t(st.st_size) - soff) / kScales) {
    std::fprintf(stderr, "row_store_open: table extent invalid for %s\n", path);
    close(s->fd);
    delete s;
    return nullptr;
  }
  if (resident_mode && numa_mode) {
    if (!load_resident_numa(s, path, size_t(st.st_size))) {
      close(s->fd);
      delete s;
      return nullptr;
    }
    budget = 0;
  } else if (resident_mode) {
    s->resident_size = size_t(st.st_size);
    void *m = mmap(nullptr, s->resident_size, PROT_READ, MAP_SHARED | MAP_POPULATE, s->fd, 0);
    if (m == MAP_FAILED) {
      std::fprintf(stderr, "row_store_open: resident mmap failed errno=%d\n", errno);
      close(s->fd);
      delete s;
      return nullptr;
    }
    s->resident = static_cast<uint8_t *>(m);
    if (mlock(s->resident, s->resident_size)) {
      std::fprintf(stderr, "row_store_open: mlock failed errno=%d (need RLIMIT_MEMLOCK)\n", errno);
      munmap(s->resident, s->resident_size);
      close(s->fd);
      delete s;
      return nullptr;
    }
    budget = 0;
  }
  s->rows = rows;
  s->weight_offset = woff;
  s->scale_offset = soff;
  s->row_lo = 0;
  s->row_hi = rows;
  s->slots = budget / kSlotBytes;
  if (s->slots) {
    void *c = mmap(nullptr, s->slots * kRow, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    void *k = mmap(nullptr, s->slots * sizeof(uint64_t), PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (c == MAP_FAILED || k == MAP_FAILED) {
      std::fprintf(stderr, "row_store_open: cache allocation failed errno=%d\n", errno);
      if (c != MAP_FAILED) munmap(c, s->slots * kRow);
      if (k != MAP_FAILED) munmap(k, s->slots * sizeof(uint64_t));
      close(s->fd);
      delete s;
      return nullptr;
    }
    s->cache = static_cast<uint8_t *>(c);
    s->keys = static_cast<uint64_t *>(k);
    if (cache_thp) madvise(s->cache, s->slots * kRow, MADV_HUGEPAGE);
    if (cache_prefault || !cache_thp) {
      const auto t_pf = std::chrono::steady_clock::now();
      if (cache_prefault) {
        prefault(s->cache, s->slots * kRow);
        prefault(s->keys, s->slots * sizeof(uint64_t));
      }
      std::fprintf(stderr, "[engram-cache] file=%s slots=%llu bytes=%llu thp=%d prefault=%d prefault_s=%.2f\n", path,
                   (unsigned long long)s->slots, (unsigned long long)(s->slots * kSlotBytes), cache_thp, cache_prefault,
                   std::chrono::duration<double>(std::chrono::steady_clock::now() - t_pf).count());
    }
  }
  if (!s->resident) io_start(s);
  return s;
}

extern "C" Store *row_store_open(const char *path, uint64_t rows, uint64_t woff,
                                 uint64_t soff, uint64_t budget, int resident_mode) {
  return row_store_open_numa(path, rows, woff, soff, budget, resident_mode, 0, -1);
}

// out[0] mode, out[1] node, out[2] sampled pages on node 0, out[3] on node 1,
// out[4] other/unknown, out[5] load ns, out[6] resident bytes,
// out[7] slot-cache address, out[8] slot-cache bytes (for tests: smaps/numa_maps)
extern "C" void row_store_numa_info(Store *s, uint64_t *out) {
  out[0] = uint64_t(s->numa_mode);
  out[1] = uint64_t(int64_t(s->numa_node));
  out[2] = s->numa_n0;
  out[3] = s->numa_n1;
  out[4] = s->numa_other;
  out[5] = s->numa_load_ns;
  out[6] = s->resident_size;
  out[7] = uint64_t(reinterpret_cast<uintptr_t>(s->cache));
  out[8] = s->slots * kRow;
}

extern "C" void row_store_lookup(void *opaque) {
  auto *work = static_cast<Work *>(opaque);
  Store *s = work->store;
  const auto t_call = std::chrono::steady_clock::now();
  // pass 1: cache hits and invalid ids are served in place; misses are
  // collected, then read concurrently, then inserted into the cache
  struct Miss { uint64_t i; int64_t id; bool ok; uint8_t row[kRow]; };
  std::vector<Miss> misses;
  misses.reserve(work->count);
  for (uint64_t i = 0; i < work->count; ++i) {
    const int64_t id = work->ids[i];
    uint8_t *w_out = work->weights + i * kDim;
    uint8_t *s_out = work->scales + i * kScales;
    if (id < 0 || uint64_t(id) >= s->rows) {
      std::memset(w_out, 0, kDim);
      std::memset(s_out, 0, kScales);
      s->errors.fetch_add(1, std::memory_order_relaxed);
      continue;
    }
    if (uint64_t(id) < s->row_lo || uint64_t(id) >= s->row_hi) {
      std::memset(w_out, 0, kDim);
      std::memset(s_out, 0, kScales);
      continue;
    }
    const uint64_t slot = s->slots ? uint64_t(id) % s->slots : 0;
    bool hit = false;
    if (s->slots) {
      std::lock_guard<std::mutex> guard(s->locks[slot % kLockShards]);
      if (s->keys[slot] == uint64_t(id) + 1) {
        std::memcpy(w_out, s->cache + slot * kRow, kDim);
        std::memcpy(s_out, s->cache + slot * kRow + kDim, kScales);
        hit = true;
      }
    }
    if (hit) {
      s->hits.fetch_add(1, std::memory_order_relaxed);
    } else {
      misses.push_back(Miss{i, id, false, {}});
    }
  }
  if (!misses.empty()) {
    const auto t_miss = std::chrono::steady_clock::now();
    if (s->resident || misses.size() == 1 || s->io.threads.empty()) {
      for (auto &m : misses)
        m.ok = read_bytes(s, s->weight_offset + uint64_t(m.id) * kDim, m.row, kDim) &&
               read_bytes(s, s->scale_offset + uint64_t(m.id) * kScales, m.row + kDim, kScales);
    } else {
      std::vector<std::function<void()>> jobs;
      jobs.reserve(misses.size());
      for (auto &m : misses)
        jobs.emplace_back([s, &m] {
          m.ok = read_bytes(s, s->weight_offset + uint64_t(m.id) * kDim, m.row, kDim) &&
                 read_bytes(s, s->scale_offset + uint64_t(m.id) * kScales, m.row + kDim, kScales);
        });
      io_run_batch(s, jobs);
    }
    s->miss_ns.fetch_add(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t_miss).count(),
                         std::memory_order_relaxed);
    for (auto &m : misses) {
      uint8_t *w_out = work->weights + m.i * kDim;
      uint8_t *s_out = work->scales + m.i * kScales;
      if (!m.ok) {
        std::memset(w_out, 0, kDim);
        std::memset(s_out, 0, kScales);
        s->errors.fetch_add(1, std::memory_order_relaxed);
        continue;
      }
      s->misses.fetch_add(1, std::memory_order_relaxed);
      if (s->slots) {
        const uint64_t slot = uint64_t(m.id) % s->slots;
        std::lock_guard<std::mutex> guard(s->locks[slot % kLockShards]);
        std::memcpy(s->cache + slot * kRow, m.row, kRow);
        s->keys[slot] = uint64_t(m.id) + 1;
      }
      std::memcpy(w_out, m.row, kDim);
      std::memcpy(s_out, m.row + kDim, kScales);
    }
  }
  s->calls.fetch_add(1, std::memory_order_relaxed);
  s->lookup_ns.fetch_add(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t_call).count(),
                         std::memory_order_relaxed);
}

extern "C" void row_store_stats(Store *s, uint64_t *out) {
  out[0] = s->hits.load();
  out[1] = s->misses.load();
  out[2] = s->reads.load();
  out[3] = s->slots * kSlotBytes;
  out[4] = s->errors.load();
  out[5] = s->slots;
  out[6] = s->calls.load();
  out[7] = s->lookup_ns.load();
  out[8] = s->miss_ns.load();
}

extern "C" void row_store_range(Store *s, uint64_t lo, uint64_t hi) {
  if (lo > hi || hi > s->rows) {
    std::fprintf(stderr, "row_store_range: invalid [%llu,%llu) for %llu rows\n",
                 (unsigned long long)lo, (unsigned long long)hi, (unsigned long long)s->rows);
    return;
  }
  s->row_lo = lo;
  s->row_hi = hi;
}

extern "C" void row_store_close(Store *s) {
  if (!s) return;
  io_stop(s);
  if (s->resident) munmap(s->resident, s->resident_size);
  if (s->slots) {
    munmap(s->cache, s->slots * kRow);
    munmap(s->keys, s->slots * sizeof(uint64_t));
  }
  if (s->fd >= 0) close(s->fd);
  delete s;
}
