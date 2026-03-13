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
Simple PubSub-layer priority_resource example.

Demonstrates:
- preemption on one resource
- context-based auto-release (resource.autorelease())
- manual acquire/release flow without context (still preempted)
'''
from dssim import DSSimulation, PriorityResource, DSResourcePreempted


def t(value):
    return round(float(value), 6)


def run_with_autorelease_context():
    sim = DSSimulation()
    machine = PriorityResource(amount=1, capacity=1, preemptive=True, name='machine', sim=sim)
    machine_probe = machine.add_stats_probe(name='usage')
    log = []

    def low_with_context():
        with machine.autorelease():
            got = yield from machine.gget(priority=5, preempt=True)
            assert got == 1
            log.append(('start', 'low', t(sim.time)))
            try:
                yield from sim.gsleep(10)
                log.append(('finish', 'low', t(sim.time)))
                return
            except DSResourcePreempted:
                log.append(('preempted', 'low', t(sim.time), 7.0))

        with machine.autorelease():
            got = yield from machine.gget(priority=5, preempt=True)
            assert got == 1
            log.append(('start', 'low', t(sim.time)))
            yield from sim.gsleep(7)
            log.append(('finish', 'low', t(sim.time)))

    def high_with_context():
        yield from sim.gsleep(3)
        with machine.autorelease():
            got = yield from machine.gget(priority=1, preempt=True)
            assert got == 1
            log.append(('start', 'high', t(sim.time)))
            yield from sim.gsleep(2)
            log.append(('finish', 'high', t(sim.time)))

    sim.schedule(0, low_with_context())
    sim.schedule(0, high_with_context())
    sim.run(30)
    stats = machine_probe.get_statistics()
    print(
        f'Summary: {machine_probe.name} '
        f'avg_amount={stats["time_avg_amount"]:.3f}, '
        f'max_amount={stats["max_amount"]}, '
        f'min_amount={stats["min_amount"]}, '
        f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
        f'full_ratio={stats["time_full_ratio"]:.3f}, '
        f'puts={stats["put_count"]}, '
        f'gets={stats["get_count"]}'
    )

    assert log[0] == ('start', 'low', 0.0)
    assert set(log[1:3]) == {('start', 'high', 3.0), ('preempted', 'low', 3.0, 7.0)}
    assert log[3:] == [
        ('finish', 'high', 5.0),
        ('start', 'low', 5.0),
        ('finish', 'low', 12.0),
    ]
    assert machine.amount == 1, f'Expected resource to be fully released, got amount={machine.amount}'
    return log


def run_without_context_manual_release():
    sim = DSSimulation()
    machine = PriorityResource(amount=1, capacity=1, preemptive=True, name='machine', sim=sim)
    machine_probe = machine.add_stats_probe(name='usage')
    log = []

    def low_manual():
        got = yield from machine.gget(priority=5, preempt=True)
        assert got == 1
        log.append(('start', 'low', t(sim.time)))
        try:
            yield from sim.gsleep(10)
            log.append(('finish', 'low', t(sim.time)))
            machine.put_nowait()
            return
        except DSResourcePreempted:
            log.append(('preempted', 'low', t(sim.time), 7.0))

        got = yield from machine.gget(priority=5, preempt=True)
        assert got == 1
        log.append(('start', 'low', t(sim.time)))
        yield from sim.gsleep(7)
        log.append(('finish', 'low', t(sim.time)))
        machine.put_nowait()

    def high_manual():
        yield from sim.gsleep(3)
        got = yield from machine.gget(priority=1, preempt=True)
        assert got == 1
        log.append(('start', 'high', t(sim.time)))
        yield from sim.gsleep(2)
        log.append(('finish', 'high', t(sim.time)))
        machine.put_nowait()

    sim.schedule(0, low_manual())
    sim.schedule(0, high_manual())
    sim.run(30)
    stats = machine_probe.get_statistics()
    print(
        f'Summary: {machine_probe.name} '
        f'avg_amount={stats["time_avg_amount"]:.3f}, '
        f'max_amount={stats["max_amount"]}, '
        f'min_amount={stats["min_amount"]}, '
        f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
        f'full_ratio={stats["time_full_ratio"]:.3f}, '
        f'puts={stats["put_count"]}, '
        f'gets={stats["get_count"]}'
    )

    assert log[0] == ('start', 'low', 0.0)
    assert set(log[1:3]) == {('start', 'high', 3.0), ('preempted', 'low', 3.0, 7.0)}
    assert log[3:] == [
        ('finish', 'high', 5.0),
        ('start', 'low', 5.0),
        ('finish', 'low', 12.0),
    ]
    assert machine.amount == 1, f'Expected resource to be fully released, got amount={machine.amount}'
    return log


if __name__ == '__main__':
    print('Demo 1: preemption with autorelease context')
    log_ctx = run_with_autorelease_context()
    print('context log:', log_ctx)

    print('\nDemo 2: preemption with manual release (no context)')
    log_manual = run_without_context_manual_release()
    print('manual log:', log_manual)
