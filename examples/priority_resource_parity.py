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
Parity examples for resource priority semantics.

Demo 1: PriorityResource parity (no interruption, only waiter ordering).
Demo 2: Preemptive parity with visible interruption events:
        SimPy PreemptiveResource vs DSSim PriorityResource(preemptive=True).
'''
from dssim import DSSimulation, PriorityResource, DSResourcePreempted

try:
    import simpy
except ImportError:  # pragma: no cover - optional dependency for examples
    simpy = None


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
    return starts


def run_simpy_non_preemptive():
    if simpy is None:
        return None

    env = simpy.Environment()
    res = simpy.PriorityResource(env, capacity=1)
    starts = []

    def customer(name, arrival, priority, service):
        yield env.timeout(arrival)
        req = res.request(priority=priority)
        yield req
        starts.append((name, env.now))
        yield env.timeout(service)
        res.release(req)

    for job in NON_PREEMPTIVE_JOBS:
        env.process(customer(*job))

    env.run(until=30)
    return starts


def run_dssim_preemptive():
    sim = DSSimulation()
    resource = PriorityResource(amount=1, capacity=1, preemptive=True, name='machine', sim=sim)
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
    return log


def run_simpy_preemptive():
    if simpy is None:
        return None

    env = simpy.Environment()
    machine = simpy.PreemptiveResource(env, capacity=1)
    log = []

    def job(name, arrival, prio, service):
        yield env.timeout(arrival)
        remaining = service
        while remaining > 0:
            with machine.request(priority=prio, preempt=True) as req:
                yield req
                yield env.timeout(ACQUIRE_SETTLE)
                start = env.now
                log.append(('start', name, tstamp(env.now)))
                try:
                    yield env.timeout(remaining)
                    remaining = 0
                    log.append(('finish', name, tstamp(env.now)))
                except simpy.Interrupt:
                    remaining -= env.now - start
                    log.append(('preempted', name, tstamp(env.now), tstamp(remaining)))

    for item in PREEMPTIVE_JOBS:
        env.process(job(*item))
    env.run(until=30)
    return log


if __name__ == '__main__':
    print('Demo 1: PriorityResource (non-preemptive)')
    dssim_starts = run_dssim_non_preemptive()
    print('DSSim starts:', dssim_starts)
    assert dssim_starts == [('low', 0), ('high', 4), ('mid', 5)]

    simpy_starts = run_simpy_non_preemptive()
    if simpy_starts is None:
        print('SimPy not installed: skipped non-preemptive SimPy parity run.')
    else:
        print('SimPy starts:', simpy_starts)
        assert simpy_starts == dssim_starts
        print('Non-preemptive parity OK.')

    print('\nDemo 2: Preemptive semantics (with interruption)')
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

    simpy_log = run_simpy_preemptive()
    if simpy_log is None:
        print('SimPy not installed: skipped preemptive SimPy parity run.')
    else:
        print('SimPy log:', simpy_log)
        simpy_times = [item[2] for item in simpy_log]
        assert len(simpy_times) == len(set(simpy_times)), 'SimPy preemptive demo should have unique event times.'
        assert simpy_log == dssim_log
        print('Preemptive parity OK.')
