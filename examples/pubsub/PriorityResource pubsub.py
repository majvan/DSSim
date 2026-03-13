# Copyright 2026- majvan (majvan@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
'''
DSSim-only parity example for priority resource semantics.

Demo 1: non-preemptive priority waiter ordering.
Demo 2: preemptive acquisition with visible interruption events.
'''
from dssim import DSSimulation, PriorityResource, DSResourcePreempted


NON_PREEMPTIVE_JOBS = [
    # name, arrival, priority, service_time
    ('low', 0, 5, 4),
    ('mid', 1, 3, 2),
    ('high', 1, 1, 1),
]


PREEMPTIVE_JOBS = [
    # name, arrival, priority, service_time
    ('low', 0, 5, 10),
    ('high', 3, 1, 2),
]

ACQUIRE_SETTLE = 0.001


def tstamp(value):
    return round(float(value), 6)


def run_dssim_non_preemptive():
    sim = DSSimulation()
    res = PriorityResource(amount=1, capacity=1, preemptive=False, name='clerks', sim=sim)
    res_probe = res.add_stats_probe(name='usage')
    starts = []

    def customer(name, arrival, priority, service):
        yield from sim.gwait(arrival)
        got = yield from res.gget(priority=priority)
        assert got == 1
        starts.append((name, sim.time))
        yield from sim.gwait(service)
        res.put_nowait()

    for job in NON_PREEMPTIVE_JOBS:
        sim.schedule(0, customer(*job))

    sim.run(30)
    stats = res_probe.get_statistics()
    print(
        f'Summary: {res_probe.name} '
        f'avg_amount={stats["time_avg_amount"]:.3f}, '
        f'max_amount={stats["max_amount"]}, '
        f'min_amount={stats["min_amount"]}, '
        f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
        f'full_ratio={stats["time_full_ratio"]:.3f}, '
        f'puts={stats["put_count"]}, '
        f'gets={stats["get_count"]}'
    )
    return starts


def run_dssim_preemptive():
    sim = DSSimulation()
    resource = PriorityResource(amount=1, capacity=1, preemptive=True, name='machine', sim=sim)
    resource_probe = resource.add_stats_probe(name='usage')
    log = []

    def job(name, arrival, prio, service):
        yield from sim.gwait(arrival)
        remaining = service
        while remaining > 0:
            with resource.autorelease():
                got = yield from resource.gget(priority=prio, preempt=True)
                assert got == 1
                yield from sim.gwait(ACQUIRE_SETTLE)
                start = sim.time
                log.append(('start', name, tstamp(sim.time)))
                try:
                    yield from sim.gwait(remaining)
                    remaining = 0
                    log.append(('finish', name, tstamp(sim.time)))
                except DSResourcePreempted:
                    remaining -= sim.time - start
                    log.append(('preempted', name, tstamp(sim.time), tstamp(remaining)))

    for item in PREEMPTIVE_JOBS:
        sim.schedule(0, job(*item))
    sim.run(30)
    stats = resource_probe.get_statistics()
    print(
        f'Summary: {resource_probe.name} '
        f'avg_amount={stats["time_avg_amount"]:.3f}, '
        f'max_amount={stats["max_amount"]}, '
        f'min_amount={stats["min_amount"]}, '
        f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
        f'full_ratio={stats["time_full_ratio"]:.3f}, '
        f'puts={stats["put_count"]}, '
        f'gets={stats["get_count"]}'
    )
    return log


if __name__ == '__main__':
    print('Demo 1: PriorityResource (non-preemptive) — DSSim')
    dssim_starts = run_dssim_non_preemptive()
    print('DSSim starts:', dssim_starts)
    assert dssim_starts == [('low', 0), ('high', 4), ('mid', 5)]
    print('Non-preemptive parity OK.')

    print('\nDemo 2: Preemptive semantics (with interruption) — DSSim')
    dssim_log = run_dssim_preemptive()
    print('DSSim log:', dssim_log)
    assert dssim_log == [
        ('start', 'low', 0.001),
        ('preempted', 'low', 3.0, 7.001),
        ('start', 'high', 3.001),
        ('finish', 'high', 5.001),
        ('start', 'low', 5.002),
        ('finish', 'low', 12.003),
    ]
    dssim_times = [item[2] for item in dssim_log]
    assert len(dssim_times) == len(set(dssim_times)), 'DSSim preemptive demo should have unique event times.'
    print('Preemptive parity OK.')
