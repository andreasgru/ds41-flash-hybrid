#!/usr/bin/env bash
# Native build entry for the pinned source tree. No GPU queries or model loads.
# Origin: own portable version of the recipe build entry. Apache-2.0.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$script_dir/runtime-config.sh"
ds41_configure
mode=${1:---print-plan}
[[ "$mode" == --print-plan || "$mode" == --build ]] || { echo BUILD_MODE_INVALID >&2; exit 2; }
build_dir="$DS41_ROOT/build/native"
source_dir="$DS41_ROOT/sources/ktransformers/kt-kernel"
configure=(cmake -S "$source_dir" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release
  -DLLAMA_AVX2=ON -DLLAMA_FMA=ON -DLLAMA_F16C=ON -DKTRANSFORMERS_USE_CUDA=ON
  "-DCMAKE_CUDA_COMPILER=$DS41_CUDA_HOME/bin/nvcc" -DCMAKE_CUDA_ARCHITECTURES=120
  "-DPYTHON_EXECUTABLE=$DS41_PYTHON" "-DCMAKE_PREFIX_PATH=$DS41_ROOT/sysroot/usr"
  "-DCMAKE_CXX_FLAGS=-I$DS41_ROOT/sysroot/usr/include -I$DS41_ROOT/sysroot/usr/include/x86_64-linux-gnu"
  "-DCMAKE_LIBRARY_PATH=$DS41_ROOT/sysroot/usr/lib/x86_64-linux-gnu")
compile=(cmake --build "$build_dir" --target kt_kernel_ext -j 1)
adapter=(g++ -std=c++17 -O2 -shared -fPIC -pthread "$DS41_ROOT/tools/engram-adapter/row_store.cpp" -o "$DS41_ROOT/tools/engram-adapter/librow_store.so")
if [[ "$mode" == --print-plan ]]; then
  printf '%q ' "${configure[@]}"; printf '\n';printf '%q ' "${compile[@]}";printf '\n';printf '%q ' "${adapter[@]}";printf '\n';exit 0
fi
[[ ! -e "$DS41_ROOT/build-manifest.json" && ! -e "$build_dir" && ! -e "$DS41_ROOT/package/kt_kernel" && ! -e "$DS41_ROOT/tools/engram-adapter/librow_store.so" ]] || { echo BUILD_DESTINATION_EXISTS >&2; exit 3; }
[[ -x "$DS41_CUDA_HOME/bin/nvcc" && -f "$source_dir/CMakeLists.txt" ]] || { echo BUILD_TOOLCHAIN_OR_SOURCE_MISSING >&2; exit 3; }
"$DS41_PYTHON" - "$script_dir" "$DS41_ROOT" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from build_manifest import source_check
source_check(Path(sys.argv[2]))
PY
export CPUINFER_PARALLEL=1 CMAKE_BUILD_PARALLEL_LEVEL=1
"${configure[@]}";"${compile[@]}";"${adapter[@]}"
suffix=$("$DS41_PYTHON" -I -c 'import sysconfig;print(sysconfig.get_config_var("EXT_SUFFIX"))')
[[ -f "$build_dir/kt_kernel_ext$suffix" ]] || { echo BUILD_EXTENSION_MISSING >&2; exit 3; }
mkdir -p "$DS41_ROOT/package"
cp -a "$source_dir/python" "$DS41_ROOT/package/kt_kernel"
cp "$build_dir/kt_kernel_ext$suffix" "$DS41_ROOT/package/kt_kernel/"
"$DS41_PYTHON" "$script_dir/build_manifest.py" create --root "$DS41_ROOT" --python "$DS41_PYTHON"
