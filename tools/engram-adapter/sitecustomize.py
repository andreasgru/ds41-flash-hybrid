"""Install the engram storage adapter and the SM120 indexer-metadata workaround
in every serving worker, only when DSV41_ENGRAM_DIR is set.

Derived from adapter/sitecustomize.py in
https://github.com/0xSero/deepseek-v4.1-flash-4x-rtx-pro-6000
Copyright (c) 2026 0xSero, MIT License. The SM120 hook is applied only if the
attributes it patches exist, so a branch that fixes it upstream is left alone.
"""

import importlib.abc
import importlib.machinery
import os
import sys

_ENGRAM = "sglang.srt.layers.engram"
_METADATA = "sglang.srt.layers.attention.dsv4.metadata"


class _Loader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        if module.__name__ == _ENGRAM:
            from engram_backend import install

            install(module)
            return
        # V4.1 ratio-1/2 indexers always call the FP4 DeepGEMM kernel. SM120
        # needs its split-128 planner even when the legacy FP8 indexer uses the
        # torch path; the upstream guard misses this case (0xSero).
        cls = getattr(module, "PagedIndexerMetadata", None)
        is_sm120 = getattr(module, "_IS_SM120", None)
        if cls is None or is_sm120 is None or not hasattr(cls, "__post_init__"):
            return
        original = cls.__post_init__

        def post_init(self):
            if module._IS_SM120 and getattr(self, "compress_ratio", None) in (1, 2):
                self.force_deep_gemm_metadata = True
            original(self)

        cls.__post_init__ = post_init


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in (_ENGRAM, _METADATA):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None:
            spec.loader = _Loader(spec.loader)
        return spec


if os.environ.get("DSV41_ENGRAM_DIR"):
    sys.meta_path.insert(0, _Finder())
