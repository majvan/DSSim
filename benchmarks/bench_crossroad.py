"""
Benchmark: crossroad simulation — all 5 implementations.

Scenarios
---------
  grid        2x2 grid, 1-hour, straight-through routing
  grid_delay  2x2 grid, 1-hour, aligned travel delays (12s EW / 15s NS)

Implementations
---------------
  dssim_pubsub    crossroad_pubsub.py       (DSSim PubSubLayer2)
  dssim_lite      crossroad_lite.py         (DSSim LiteLayer2)
  dssim_direct    crossroad_lite_direct.py  (DSSim LiteLayer2, direct ISubscriber)
  simpy           crossroad_simpy.py        (SimPy 4.x)
  salabim         crossroad_salabim.py      (salabim)
"""
import sys
import os
import time
import statistics
import argparse
from io import StringIO
from contextlib import redirect_stdout, contextmanager

# Make the projects dir importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'projects'))

import crossroad_pubsub       as pubsub_mod
import crossroad_lite         as lite_mod
import crossroad_lite_direct  as direct_mod
import crossroad_simpy        as simpy_mod
import crossroad_salabim      as salabim_mod
from dssim.timequeue import TQBinTree, TQBisect

RUNS = 30
SIM_TIME = 3600


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Crossroad benchmark across DSSim PubSub/Lite/direct, SimPy, and salabim.',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'grid', 'grid-delay'],
        default='all',
        help='Run only a selected scenario (default: all).',
    )
    return parser.parse_args()


def bench(label, fn, runs=RUNS):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        with redirect_stdout(StringIO()):
            fn()
        times.append(time.perf_counter() - t0)
    med  = statistics.median(times)
    mean = statistics.mean(times)
    stdev = statistics.stdev(times)
    print(f"  {label:<22}  median={med*1000:7.1f} ms  mean={mean*1000:7.1f} ms  stdev={stdev*1000:6.1f} ms  ({runs} runs)")
    return med


@contextmanager
def _with_timequeue(module, tq_cls):
    '''Temporarily force DSSimulation default timequeue class in module.'''
    base_cls = module.DSSimulation

    class _DSSimulationWithTQ(base_cls):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('timequeue', tq_cls)
            super().__init__(*args, **kwargs)

    module.DSSimulation = _DSSimulationWithTQ
    try:
        yield
    finally:
        module.DSSimulation = base_cls


def bench_dssim_tq(label_base, module, fn):
    rows = []
    for tq_name, tq_cls in (('TQBinTree', TQBinTree), ('TQBisect', TQBisect)):
        with _with_timequeue(module, tq_cls):
            label = f'{label_base}[{tq_name}]'
            rows.append((label, bench(label, fn)))
    return rows


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


if __name__ == '__main__':
    args = _parse_args()
    run_all = args.scenario == 'all'

    if run_all or args.scenario == 'grid':
        section("Scenario: 2x2 grid, straight-through, 1 hour")
        dssim_rows = []
        dssim_rows.extend(bench_dssim_tq("dssim_pubsub ", pubsub_mod, lambda: pubsub_mod.run_grid(SIM_TIME, pubsub_mod.DEFAULT_ROUTING)))
        dssim_rows.extend(bench_dssim_tq("dssim_lite   ", lite_mod,   lambda: lite_mod.run_grid(SIM_TIME, lite_mod.DEFAULT_ROUTING)))
        dssim_rows.extend(bench_dssim_tq("dssim_lite_direct", direct_mod, lambda: direct_mod.run_grid(SIM_TIME, direct_mod.DEFAULT_ROUTING)))
        r_simpy   = bench("simpy",   lambda: simpy_mod.run_grid(SIM_TIME, simpy_mod.DEFAULT_ROUTING))
        r_salabim = bench("salabim", lambda: salabim_mod.run_grid(SIM_TIME, salabim_mod.DEFAULT_ROUTING))

        fastest = min([t for _, t in dssim_rows] + [r_simpy, r_salabim])
        print(f"\n  relative to fastest ({fastest*1000:.1f} ms):")
        for name, t in dssim_rows + [("simpy", r_simpy), ("salabim", r_salabim)]:
            print(f"    {name:<22}  {t/fastest:.2f}x")

    if run_all or args.scenario == 'grid-delay':
        section("Scenario: 2x2 grid, aligned delays (12s EW / 15s NS), 1 hour")
        dssim_rows_d = []
        dssim_rows_d.extend(bench_dssim_tq("dssim_pubsub ", pubsub_mod, lambda: pubsub_mod.run_grid_with_delays(SIM_TIME, pubsub_mod.DEFAULT_ROUTING, 12, 15)))
        dssim_rows_d.extend(bench_dssim_tq("dssim_lite   ", lite_mod,   lambda: lite_mod.run_grid_with_delays(SIM_TIME, lite_mod.DEFAULT_ROUTING, 12, 15)))
        dssim_rows_d.extend(bench_dssim_tq("dssim_lite_direct", direct_mod, lambda: direct_mod.run_grid_with_delays(SIM_TIME, direct_mod.DEFAULT_ROUTING, 12, 15)))
        r_simpy_d   = bench("simpy",   lambda: simpy_mod.run_grid_with_delays(SIM_TIME, simpy_mod.DEFAULT_ROUTING, 12, 15))
        r_salabim_d = bench("salabim", lambda: salabim_mod.run_grid_with_delays(SIM_TIME, salabim_mod.DEFAULT_ROUTING, 12, 15))

        fastest_d = min([t for _, t in dssim_rows_d] + [r_simpy_d, r_salabim_d])
        print(f"\n  relative to fastest ({fastest_d*1000:.1f} ms):")
        for name, t in dssim_rows_d + [("simpy", r_simpy_d), ("salabim", r_salabim_d)]:
            print(f"    {name:<22}  {t/fastest_d:.2f}x")

    print()
