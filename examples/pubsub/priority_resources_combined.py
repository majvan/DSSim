#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
'''
Preemptive get_cond example with two resources.

This demonstrates two phases using check_and_wait + filter circuits:
1) OR filtering: immediate acquire (waiting time == 0)
2) AND filtering: blocked acquire (waiting time > 0)

The resources are preemptive DSPriorityResource instances.

For a nested ownership/preemption example, see priority_resources_nested.py.
'''

from dssim import DSSimulation, DSResourcePreempted
from dssim.pubsub.base import TestObject


def main() -> None:
    sim = DSSimulation()
    cpu = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='cpu')
    io = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='io')
    cpu_probe = cpu.add_stats_probe(name='usage')
    io_probe = io.add_stats_probe(name='usage')
    preempted_at = {'time': None}

    async def cpu_low_holder():
        # Lower priority holder; gets preempted by the high-priority requester.
        with cpu.autorelease():
            got = await cpu.get(priority=5, preempt=True)
            assert got == 1
            try:
                await sim.wait(float('inf'))
            except DSResourcePreempted:
                preempted_at['time'] = sim.time

    async def io_blocker_same_priority():
        # Same priority as requester -> cannot be preempted by it.
        with io.autorelease():
            got = await io.get(priority=1, preempt=True)
            assert got == 1
            await sim.wait(4)

    async def requester():
        await sim.wait(1)
        f_cpu = sim.filter(cpu.get_cond(priority=1, preempt=True))
        f_io = sim.filter(io.get_cond(priority=1, preempt=True))

        # ------------------------------------------------------------------
        # Phase 1: OR filtering; should be immediate (0 wait)
        # ------------------------------------------------------------------
        t0 = sim.time
        got_or = await (f_cpu | f_io).check_and_wait(5)
        wait_or = sim.time - t0

        assert wait_or == 0, f'OR wait expected 0, got {wait_or}'
        assert got_or == {f_cpu: TestObject}, f'Unexpected OR result: {got_or}'
        assert got_or[f_cpu] is TestObject
        resource_or = f_cpu.cond.resource
        assert resource_or is cpu
        assert resource_or.held_amount(sim.pid) == 1

        # ------------------------------------------------------------------
        # Phase 2: AND filtering; must block (> 0 wait)
        # ------------------------------------------------------------------
        # Keep this first resource held: the AND phase reuses the same filter
        # instance/state and only needs to acquire the second resource.
        t1 = sim.time
        got_and = await (f_cpu & f_io).check_and_wait(10)
        wait_and = sim.time - t1

        assert wait_and == 3, f'AND wait expected 3, got {wait_and}'
        assert preempted_at['time'] is not None, 'Expected low holder to be preempted.'
        assert preempted_at['time'] == 1, f'Expected preemption at t=1, got {preempted_at["time"]}'
        assert got_and == {f_cpu: TestObject, f_io: io.tx_nempty}, f'Unexpected AND result: {got_and}'
        resources_and = {flt.cond.resource for flt in got_and.keys()}
        assert resources_and == {cpu, io}
        assert cpu.held_amount(sim.pid) == 1
        assert io.held_amount(sim.pid) == 1
        cpu.put_nowait()
        io.put_nowait()

        # ------------------------------------------------------------------
        # Phase 3: OR filtering; blocked wait with exact non-zero delta
        # ------------------------------------------------------------------
        ready = sim.queue()

        async def cpu_blocker():
            with cpu.autorelease():
                got = await cpu.get(priority=1, preempt=True)
                assert got == 1
                ready.put_nowait('cpu')
                await sim.wait(10)

        async def io_blocker():
            with io.autorelease():
                got = await io.get(priority=1, preempt=True)
                assert got == 1
                ready.put_nowait('io')
                await sim.wait(2)

        sim.schedule(0, cpu_blocker())
        sim.schedule(0, io_blocker())
        got_ready0 = await ready.get()
        got_ready1 = await ready.get()
        assert {got_ready0, got_ready1} == {'cpu', 'io'}

        f_cpu = sim.filter(cpu.get_cond(priority=1, preempt=True))
        f_io = sim.filter(io.get_cond(priority=1, preempt=True))
        t2 = sim.time
        got_or_blocked = await (f_cpu | f_io).check_and_wait(10)
        wait_or_blocked = sim.time - t2

        assert wait_or_blocked == 2, f'Blocked OR wait expected 2, got {wait_or_blocked}'
        assert got_or_blocked == {f_io: io.tx_nempty}, f'Unexpected blocked OR result: {got_or_blocked}'
        resource_blocked = f_io.cond.resource
        assert resource_blocked is io
        assert resource_blocked.held_amount(sim.pid) == 1
        resource_blocked.put_nowait()

        print(f'OR wait: {wait_or}')
        print(f'AND wait: {wait_and}')
        print(f'OR blocked wait: {wait_or_blocked}')

    sim.schedule(0, cpu_low_holder())
    sim.schedule(0, io_blocker_same_priority())
    sim.schedule(0, requester())
    sim.run(20)
    for probe in (cpu_probe, io_probe):
        stats = probe.get_statistics()
        print(
            f'Summary: {probe.name} '
            f'avg_amount={stats["time_avg_amount"]:.3f}, '
            f'max_amount={stats["max_amount"]}, '
            f'min_amount={stats["min_amount"]}, '
            f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
            f'full_ratio={stats["time_full_ratio"]:.3f}, '
            f'puts={stats["put_count"]}, '
            f'gets={stats["get_count"]}, '
            f'preempts={stats["preempt_count"]}, '
            f'preempted_amount={stats["preempted_amount"]}'
        )

if __name__ == '__main__':
    main()
