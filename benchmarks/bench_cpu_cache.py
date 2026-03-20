"""
Benchmark: CPU cache hierarchy simulation — DSSim LiteLayer2 vs SimPy vs salabim.

Scenarios
---------
  single    1 core,  300 000 accesses  — sequential baseline
  multi     16 cores, 20 000 accesses each — L2 contention, concurrent events
  irq       1 core,  200 000 accesses + periodic ISR — interrupt overhead

DSSim is benchmarked with both TQBinTree (BT) and TQBisect (Bi).

The multi-core scenario creates concurrent events at the same simulation
timestamp (all cores sleep for L1/L2/RAM cycles simultaneously), which is
where TQBinTree's bucketed-event design shows its advantage over TQBisect
and where DSSim's overhead ratio vs SimPy narrows.
"""
import sys
import os
import time
import statistics
import argparse
from io import StringIO
from contextlib import redirect_stdout, contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'projects'))

import cpu_cache_lite    as lite_mod
import cpu_cache_pubsub  as pubsub_mod
from dssim.timequeue import TQBinTree, TQBisect

RUNS    = 5
N_S     = 300_000   # single-core accesses  (~30 s total for this scenario)
N_M     = 20_000    # per-core accesses for multi-core  (~30 s total)
N_IRQ   = 200_000   # accesses for IRQ scenario
N_CORES = 16
SEED    = 42


def _parse_args():
    parser = argparse.ArgumentParser(
        description='CPU cache benchmark for DSSim Lite vs SimPy vs salabim.',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'single', 'multi', 'irq-single', 'irq-multi'],
        default='all',
        help='Run only a selected scenario (default: all).',
    )
    parser.add_argument(
        '--with-simpy',
        action='store_true',
        help='Include SimPy benchmark rows.',
    )
    parser.add_argument(
        '--with-salabim',
        action='store_true',
        help='Include salabim benchmark rows (IRQ scenarios).',
    )
    return parser.parse_args()


# ── Timing helpers ─────────────────────────────────────────────────────────
def bench(label, fn, runs=RUNS):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        with redirect_stdout(StringIO()):
            fn()
        times.append(time.perf_counter() - t0)
    med   = statistics.median(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<26}  median={med*1000:7.1f} ms  stdev={stdev*1000:5.1f} ms  ({runs} runs)")
    return med


@contextmanager
def _with_timequeue(module, tq_cls):
    """Temporarily patch DSSimulation in the given module to use tq_cls."""
    base_cls = module.DSSimulation

    class _DSSimWithTQ(base_cls):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('timequeue', tq_cls)
            super().__init__(*args, **kwargs)

    module.DSSimulation = _DSSimWithTQ
    try:
        yield
    finally:
        module.DSSimulation = base_cls


def bench_dssim_tq(label_base, module, fn):
    rows = []
    for tq_name, tq_cls in (('BT', TQBinTree), ('Bi', TQBisect)):
        with _with_timequeue(module, tq_cls):
            label = f'{label_base}[{tq_name}]'
            rows.append((label, bench(label, fn)))
    return rows


def section(title):
    print(f"\n{'='*64}")
    print(f"  {title}")
    print(f"{'='*64}")


def summary(rows):
    print(f"\n  {'Implementation':<26}  {'median ms':>10}")
    print(f"  {'─'*40}")
    for name, t in rows:
        print(f"  {name:<26}  {t*1000:>10.1f}")


if __name__ == '__main__':
    args = _parse_args()
    run_all = args.scenario == 'all'
    include_simpy = args.with_simpy
    include_salabim = args.with_salabim
    simpy_mod = None
    salabim_mod = None

    if include_simpy:
        try:
            import cpu_cache_simpy as simpy_mod  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(
                f'Cannot use --with-simpy: missing dependency while importing cpu_cache_simpy ({exc}).'
            ) from exc

    if include_salabim:
        try:
            import cpu_cache_salabim as salabim_mod  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(
                f'Cannot use --with-salabim: missing dependency while importing cpu_cache_salabim ({exc}).'
            ) from exc

    rows_s = None
    rows_s_ps = None
    r_simpy_s = None
    rows_m = None
    rows_m_ps = None
    r_simpy_m = None

    # ── Scenario 1: single core ─────────────────────────────────────────────
    if run_all or args.scenario == 'single':
        section(f"Scenario: single core, mixed workload  N={N_S:,}")
        wl_single = lite_mod.make_workload(N_S, seed=SEED)
        rows_s = bench_dssim_tq('dssim_lite', lite_mod, lambda: lite_mod._run_one(wl_single))
        rows_s_ps = bench_dssim_tq('dssim_pubsub', pubsub_mod, lambda: pubsub_mod._run_one(wl_single))
        rows_single_all = rows_s + rows_s_ps
        if include_simpy:
            r_simpy_s = bench('simpy', lambda: simpy_mod._run_one(wl_single))
            rows_single_all.append(('simpy', r_simpy_s))
        summary(rows_single_all)

    # ── Scenario 2: 16 cores, shared L2 contention ─────────────────────────
    if run_all or args.scenario == 'multi':
        section(f"Scenario: {N_CORES} cores sharing L2  {N_CORES}×{N_M:,} accesses")
        rows_m = bench_dssim_tq('dssim_lite', lite_mod,
            lambda: lite_mod.run(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
        rows_m_ps = bench_dssim_tq('dssim_pubsub', pubsub_mod,
            lambda: pubsub_mod.run(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
        rows_multi_all = rows_m + rows_m_ps
        if include_simpy:
            r_simpy_m = bench('simpy',
                lambda: simpy_mod.run(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
            rows_multi_all.append(('simpy', r_simpy_m))
        summary(rows_multi_all)

    # ── Scaling table ───────────────────────────────────────────────────────
    if rows_s is not None and rows_m is not None and rows_s_ps is not None and rows_m_ps is not None:
        section(f"Scaling: single → {N_CORES} cores")
        single_map = {name: t for name, t in rows_s + rows_s_ps}
        multi_map  = {name: t for name, t in rows_m + rows_m_ps}
        print(f"\n  {'Implementation':<26}  {'single ms':>10}  {'multi ms':>10}  {'scale':>7}")
        print(f"  {'─'*58}")
        for name in [n for n, _ in rows_s + rows_s_ps]:
            s = single_map[name]
            m = multi_map[name]
            print(f"  {name:<26}  {s*1000:>10.1f}  {m*1000:>10.1f}  {m/s:>6.2f}x")
        if include_simpy and r_simpy_s is not None and r_simpy_m is not None:
            print(f"  {'simpy':<26}  {r_simpy_s*1000:>10.1f}  {r_simpy_m*1000:>10.1f}  {r_simpy_m/r_simpy_s:>6.2f}x")

    # ── Scenario 3: IRQ — 1 core + periodic ISR ────────────────────────────
    if run_all or args.scenario == 'irq-single':
        section(f"Scenario: IRQ  N={N_IRQ:,}  (1 core, ~{N_IRQ // 40:,} IRQs expected)")
        rows_irq = bench_dssim_tq('dssim_lite+irq', lite_mod,
            lambda: lite_mod.run_with_irq(n_accesses=N_IRQ, seed=SEED))
        rows_irq_all = list(rows_irq)
        r_simpy_irq = None
        r_salabim_irq = None
        if include_simpy:
            r_simpy_irq = bench('simpy+irq',
                lambda: simpy_mod.run_with_irq(n_accesses=N_IRQ, seed=SEED))
            rows_irq_all.append(('simpy+irq', r_simpy_irq))
        if include_salabim:
            r_salabim_irq = bench('salabim+irq',
                lambda: salabim_mod.run_with_irq(n_accesses=N_IRQ, seed=SEED))
            rows_irq_all.append(('salabim+irq', r_salabim_irq))

        if include_salabim and r_salabim_irq is not None:
            summary(rows_irq_all)
        elif include_simpy and r_simpy_irq is not None:
            summary(rows_irq_all)
        else:
            summary(rows_irq_all)

        if rows_s is not None and include_simpy and r_simpy_s is not None and r_simpy_irq is not None:
            print()
            irq_no_irq_s = {n: t for n, t in rows_s}
            irq_no_irq_i = {n: t for n, t in rows_irq}
            print(f"\n  IRQ overhead  (irq_N={N_IRQ:,} vs single_N={N_S:,}, scaled to same N)")
            print(f"  {'─'*52}")
            for name_s, name_i in [('dssim_lite[BT]', 'dssim_lite+irq[BT]'),
                                    ('dssim_lite[Bi]', 'dssim_lite+irq[Bi]')]:
                t_s = irq_no_irq_s[name_s] * (N_IRQ / N_S)
                t_i = irq_no_irq_i[name_i]
                print(f"  {name_i:<26}  base={t_s*1000:6.1f} ms  irq={t_i*1000:6.1f} ms  overhead={t_i/t_s - 1:+.1%}")
            t_simpy_base = r_simpy_s * (N_IRQ / N_S)
            print(f"  {'simpy+irq':<26}  base={t_simpy_base*1000:6.1f} ms  irq={r_simpy_irq*1000:6.1f} ms  overhead={r_simpy_irq/t_simpy_base - 1:+.1%}")

    # ── Scenario 4: IRQ — 16 cores + periodic ISR ──────────────────────────
    if run_all or args.scenario == 'irq-multi':
        section(f"Scenario: IRQ  {N_CORES} cores × {N_M:,} accesses")

        rows_irq_m = bench_dssim_tq('dssim_lite+irq', lite_mod,
            lambda: lite_mod.run_with_irq(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
        rows_irq_m_all = list(rows_irq_m)
        r_simpy_irq_m = None
        r_salabim_irq_m = None
        if include_simpy:
            r_simpy_irq_m = bench('simpy+irq',
                lambda: simpy_mod.run_with_irq(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
            rows_irq_m_all.append(('simpy+irq', r_simpy_irq_m))
        if include_salabim:
            r_salabim_irq_m = bench('salabim+irq',
                lambda: salabim_mod.run_with_irq(n_cores=N_CORES, n_accesses=N_M, seed=SEED))
            rows_irq_m_all.append(('salabim+irq', r_salabim_irq_m))

        if include_salabim and r_salabim_irq_m is not None:
            summary(rows_irq_m_all)
        elif include_simpy and r_simpy_irq_m is not None:
            summary(rows_irq_m_all)
        else:
            summary(rows_irq_m_all)

        if rows_m is not None and include_simpy and r_simpy_m is not None and r_simpy_irq_m is not None:
            print()
            irq_m_map = {n: t for n, t in rows_irq_m}
            print(f"\n  IRQ multi-core overhead  (vs no-IRQ multi-core, same N)")
            print(f"  {'─'*58}")
            for name_m, name_i in [('dssim_lite[BT]', 'dssim_lite+irq[BT]'),
                                    ('dssim_lite[Bi]', 'dssim_lite+irq[Bi]')]:
                t_m = {n: t for n, t in rows_m}[name_m]
                t_i = irq_m_map[name_i]
                print(f"  {name_i:<26}  no-irq={t_m*1000:6.1f} ms  irq={t_i*1000:6.1f} ms  overhead={t_i/t_m - 1:+.1%}")
            print(f"  {'simpy+irq':<26}  no-irq={r_simpy_m*1000:6.1f} ms  irq={r_simpy_irq_m*1000:6.1f} ms  overhead={r_simpy_irq_m/r_simpy_m - 1:+.1%}")

    print()
