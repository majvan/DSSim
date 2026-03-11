#!/usr/bin/env python3
'''
Preemptive take_cond example with two resources.

This demonstrates two phases using check_and_wait + filter circuits:
1) OR filtering: immediate acquire (waiting time == 0)
2) AND filtering: blocked acquire (waiting time > 0)

The resources are preemptive PriorityResource instances.
'''

from dssim import DSSimulation, PriorityResource, DSResourcePreempted, Queue
from dssim.process import _TestObject


def main() -> None:
    sim = DSSimulation()
    cpu = PriorityResource(amount=1, capacity=1, preemptive=True, name='cpu', sim=sim)
    io = PriorityResource(amount=1, capacity=1, preemptive=True, name='io', sim=sim)
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
        f_cpu = sim.filter(cpu.take_cond(priority=1, preempt=True))
        f_io = sim.filter(io.take_cond(priority=1, preempt=True))

        # ------------------------------------------------------------------
        # Phase 1: OR filtering; should be immediate (0 wait)
        # ------------------------------------------------------------------
        t0 = sim.time
        with sim.consume(cpu.tx_nempty), sim.consume(io.tx_nempty):
            got_or = await sim.check_and_wait(5, cond=f_cpu | f_io)
        wait_or = sim.time - t0

        assert wait_or == 0, f'OR wait expected 0, got {wait_or}'
        assert got_or == {f_cpu: _TestObject}, f'Unexpected OR result: {got_or}'
        assert got_or[f_cpu] is _TestObject
        resource_or = f_cpu.cond.resource
        assert resource_or is cpu
        assert resource_or.held_amount(sim.pid) == 1

        # ------------------------------------------------------------------
        # Phase 2: AND filtering; must block (> 0 wait)
        # ------------------------------------------------------------------
        # Keep this first resource held: the AND phase reuses the same filter
        # instance/state and only needs to acquire the second resource.
        t1 = sim.time
        with sim.consume(cpu.tx_nempty), sim.consume(io.tx_nempty):
            got_and = await sim.check_and_wait(10, cond=f_cpu & f_io)
        wait_and = sim.time - t1

        assert wait_and == 3, f'AND wait expected 3, got {wait_and}'
        assert preempted_at['time'] is not None, 'Expected low holder to be preempted.'
        assert preempted_at['time'] == 1, f'Expected preemption at t=1, got {preempted_at["time"]}'
        assert got_and == {f_cpu: _TestObject, f_io: io.tx_nempty}, f'Unexpected AND result: {got_and}'
        resources_and = {flt.cond.resource for flt in got_and.keys()}
        assert resources_and == {cpu, io}
        assert cpu.held_amount(sim.pid) == 1
        assert io.held_amount(sim.pid) == 1
        cpu.put_nowait()
        io.put_nowait()

        # ------------------------------------------------------------------
        # Phase 3: OR filtering; blocked wait with exact non-zero delta
        # ------------------------------------------------------------------
        ready = Queue(sim=sim)

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

        f_cpu = sim.filter(cpu.take_cond(priority=1, preempt=True))
        f_io = sim.filter(io.take_cond(priority=1, preempt=True))
        t2 = sim.time
        with sim.consume(cpu.tx_nempty), sim.consume(io.tx_nempty):
            got_or_blocked = await sim.check_and_wait(10, cond=f_cpu | f_io)
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


if __name__ == '__main__':
    main()
