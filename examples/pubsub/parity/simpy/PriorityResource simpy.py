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
SimPy-only parity example for priority/preemptive resource semantics.

Demo 1: non-preemptive priority waiter ordering.
Demo 2: preemptive acquisition with visible interruption events.

Switch backend:
- --backend simpy (default)
- --backend dssim
'''
from _backend import import_simpy_backend

simpy, BACKEND = import_simpy_backend()


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


def run_simpy_non_preemptive():
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


def run_simpy_preemptive():
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
    print(f'Demo 1: DSPriorityResource (non-preemptive) — backend={BACKEND}')
    simpy_starts = run_simpy_non_preemptive()
    print('SimPy starts:', simpy_starts)
    assert simpy_starts == [('low', 0), ('high', 4), ('mid', 5)]
    print('Non-preemptive parity OK.')

    print(f'\nDemo 2: Preemptive semantics (with interruption) — backend={BACKEND}')
    simpy_log = run_simpy_preemptive()
    print('SimPy log:', simpy_log)
    assert simpy_log == [
        ('start', 'low', 0.001),
        ('preempted', 'low', 3.0, 7.001),
        ('start', 'high', 3.001),
        ('finish', 'high', 5.001),
        ('start', 'low', 5.002),
        ('finish', 'low', 12.003),
    ]
    simpy_times = [item[2] for item in simpy_log]
    assert len(simpy_times) == len(set(simpy_times)), 'SimPy preemptive demo should have unique event times.'
    print('Preemptive parity OK.')
