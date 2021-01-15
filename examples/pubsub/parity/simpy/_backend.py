#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
'''
Backend selector for parity examples.

Supported backends:
- simpy  (real SimPy package)
- dssim  (dssim.pubsub.parity.simpy adapter)
'''
from __future__ import annotations

import os
import sys
from typing import Tuple


def _extract_backend_arg() -> str | None:
    argv = sys.argv
    for idx, arg in enumerate(list(argv)):
        if arg.startswith('--backend='):
            value = arg.split('=', 1)[1].strip().lower()
            del argv[idx]
            return value
        if arg == '--backend':
            if idx + 1 >= len(argv):
                raise SystemExit('Missing value for --backend. Use: simpy or dssim.')
            value = argv[idx + 1].strip().lower()
            del argv[idx:idx + 2]
            return value
    return None


def import_simpy_backend() -> Tuple[object, str]:
    backend = _extract_backend_arg()
    if backend is None:
        backend = os.environ.get('DSSIM_PARITY_BACKEND', 'simpy').strip().lower()

    if backend == 'dssim':
        from dssim.pubsub.parity import simpy as backend_mod
        return backend_mod, backend
    if backend == 'simpy':
        try:
            import simpy as backend_mod
        except ImportError as exc:
            raise SystemExit(
                'SimPy backend requested but package is not installed. '
                'Install with: pip install simpy, or use --backend dssim.'
            ) from exc
        return backend_mod, backend
    raise SystemExit(f'Unsupported backend {backend!r}. Use --backend simpy or --backend dssim.')
