"""
Benchmark: network packet switch simulation implementations.

Scenarios
---------
  s1-fifo      Scenario 1, FIFO output queue
  s1-priority  Scenario 1, priority output queue
  s2-credit    Scenario 2, credit-based flow control

Implementations
---------------
  dssim_pubsub      projects/network_switch.py
  dssim_lite_direct projects/network_switch_lite_direct.py
  simpy             projects/network_switch_simpy.py      (optional)
  salabim           projects/network_switch_salabim.py    (optional)

DSSim implementations are benchmarked with both TQBinTree (BT) and TQBisect (Bi).
"""
import argparse
import os
import statistics
import sys
import time
from contextlib import contextmanager, redirect_stdout
from io import StringIO

from dssim.base_components import DSKeyOrder
from dssim.timequeue import TQBinTree, TQBisect


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'projects'))

import network_switch as pubsub_mod
import network_switch_lite_direct as direct_mod


DEFAULT_RUNS = 10


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Network switch benchmark across DSSim PubSub/Lite direct, SimPy, and salabim.',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 's1-fifo', 's1-priority', 's2-credit'],
        default='all',
        help='Run only a selected scenario (default: all).',
    )
    parser.add_argument(
        '--runs',
        type=int,
        default=DEFAULT_RUNS,
        help=f'Number of benchmark repetitions (default: {DEFAULT_RUNS}).',
    )
    parser.add_argument(
        '--with-simpy',
        action='store_true',
        help='Include SimPy benchmark rows.',
    )
    parser.add_argument(
        '--with-salabim',
        action='store_true',
        help='Include salabim benchmark rows.',
    )
    parser.add_argument(
        '--fair-pubsub',
        action='store_true',
        help='Run DSSim pubsub in fair perf mode (no queue probe, direct hot-path callbacks).',
    )
    return parser.parse_args()


def bench(label, fn, runs):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        with redirect_stdout(StringIO()):
            fn()
        times.append(time.perf_counter() - t0)
    med = statistics.median(times)
    mean = statistics.mean(times)
    stdev = statistics.stdev(times) if len(times) > 1 else 0.0
    print(
        f"  {label:<26}  median={med*1000:7.1f} ms  "
        f"mean={mean*1000:7.1f} ms  stdev={stdev*1000:6.1f} ms  ({runs} runs)"
    )
    return med


@contextmanager
def _with_timequeue(module, tq_cls):
    """Temporarily force DSSimulation default timequeue class in module."""
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


def bench_dssim_tq(label_base, module, fn, runs):
    rows = []
    for tq_name, tq_cls in (('BT', TQBinTree), ('Bi', TQBisect)):
        with _with_timequeue(module, tq_cls):
            label = f'{label_base}[{tq_name}]'
            rows.append((label, bench(label, fn, runs)))
    return rows


def section(title):
    print(f"\n{'='*68}")
    print(f"  {title}")
    print(f"{'='*68}")


def summary(rows):
    print(f"\n  {'Implementation':<26}  {'median ms':>10}")
    print(f"  {'-'*40}")
    for name, t in rows:
        print(f"  {name:<26}  {t*1000:>10.1f}")


def _scenario1_fifo(
    pubsub, direct, simpy_mod, salabim_mod, runs, include_simpy, include_salabim, fair_pubsub=False,
):
    section("Scenario 1: QoS queueing (FIFO)")
    rows = []
    pubsub_label = 'dssim_pubsub_fair' if fair_pubsub else 'dssim_pubsub'
    rows.extend(
        bench_dssim_tq(
            pubsub_label, pubsub,
            lambda: pubsub.run_scenario1(fair_perf_mode=fair_pubsub),
            runs,
        )
    )
    rows.extend(bench_dssim_tq('dssim_lite_direct', direct, lambda: direct.run_scenario1(), runs))
    if include_simpy:
        rows.append(('simpy', bench('simpy', lambda: simpy_mod.run_scenario1(priority_mode=False), runs)))
    if include_salabim:
        rows.append(('salabim', bench('salabim', lambda: salabim_mod.run_scenario1(priority_mode=False), runs)))
    summary(rows)


def _scenario1_priority(
    pubsub, direct, simpy_mod, salabim_mod, runs, include_simpy, include_salabim, fair_pubsub=False,
):
    section("Scenario 1: QoS queueing (priority)")
    rows = []
    pubsub_label = 'dssim_pubsub_fair' if fair_pubsub else 'dssim_pubsub'
    rows.extend(
        bench_dssim_tq(
            pubsub_label,
            pubsub,
            lambda: pubsub.run_scenario1(
                policy=DSKeyOrder(key=lambda p: p.priority),
                fair_perf_mode=fair_pubsub,
            ),
            runs,
        )
    )
    rows.extend(
        bench_dssim_tq(
            'dssim_lite_direct',
            direct,
            lambda: direct.run_scenario1(policy=DSKeyOrder(key=lambda p: p.priority)),
            runs,
        )
    )
    if include_simpy:
        rows.append(('simpy', bench('simpy', lambda: simpy_mod.run_scenario1(priority_mode=True), runs)))
    if include_salabim:
        rows.append(('salabim', bench('salabim', lambda: salabim_mod.run_scenario1(priority_mode=True), runs)))
    summary(rows)


def _scenario2_credit(
    pubsub, direct, simpy_mod, salabim_mod, runs, include_simpy, include_salabim, fair_pubsub=False,
):
    section("Scenario 2: Credit-based flow control")
    rows = []
    pubsub_label = 'dssim_pubsub_fair' if fair_pubsub else 'dssim_pubsub'
    rows.extend(
        bench_dssim_tq(
            pubsub_label, pubsub,
            lambda: pubsub.run_scenario2(fair_perf_mode=fair_pubsub),
            runs,
        )
    )
    rows.extend(bench_dssim_tq('dssim_lite_direct', direct, lambda: direct.run_scenario2(), runs))
    if include_simpy:
        rows.append(('simpy', bench('simpy', lambda: simpy_mod.run_scenario2(), runs)))
    if include_salabim:
        rows.append(('salabim', bench('salabim', lambda: salabim_mod.run_scenario2(), runs)))
    summary(rows)


if __name__ == '__main__':
    args = _parse_args()
    runs = args.runs
    run_all = args.scenario == 'all'
    include_simpy = args.with_simpy
    include_salabim = args.with_salabim
    fair_pubsub = args.fair_pubsub
    simpy_mod = None
    salabim_mod = None

    if include_simpy:
        try:
            import network_switch_simpy as simpy_mod  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(
                f'Cannot use --with-simpy: missing dependency while importing network_switch_simpy ({exc}).'
            ) from exc

    if include_salabim:
        try:
            import network_switch_salabim as salabim_mod  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(
                f'Cannot use --with-salabim: missing dependency while importing network_switch_salabim ({exc}).'
            ) from exc

    if run_all or args.scenario == 's1-fifo':
        _scenario1_fifo(
            pubsub_mod, direct_mod, simpy_mod, salabim_mod, runs, include_simpy, include_salabim,
            fair_pubsub=fair_pubsub,
        )

    if run_all or args.scenario == 's1-priority':
        _scenario1_priority(
            pubsub_mod, direct_mod, simpy_mod, salabim_mod, runs, include_simpy, include_salabim,
            fair_pubsub=fair_pubsub,
        )

    if run_all or args.scenario == 's2-credit':
        _scenario2_credit(
            pubsub_mod, direct_mod, simpy_mod, salabim_mod, runs, include_simpy, include_salabim,
            fair_pubsub=fair_pubsub,
        )

    print()
