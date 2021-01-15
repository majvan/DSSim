#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
'''
Nested ownership on two preemptive priority resources.

Demonstrates resource-specific preemption catches:
- the process holds r0, then nested holds r1
- another process preempts only r0
- outer except r0.Preempted catches it
- inner except r1.Preempted is not triggered in this scenario
'''

from dssim import DSSimulation


def main() -> None:
    sim = DSSimulation()
    r0 = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='r0')
    r1 = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='r1')
    r0_probe = r0.add_stats_probe(name='usage')
    r1_probe = r1.add_stats_probe(name='usage')
    log = []

    async def nested_owner():
        try:
            with r0.autorelease():
                got0 = await r0.get(priority=5, preempt=True)
                assert got0 == 1
                try:
                    with r1.autorelease():
                        got1 = await r1.get(priority=10, preempt=True)
                        assert got1 == 1
                        await sim.wait(20)
                except r1.Preempted:
                    # This does not happen in this scenario; r0 is preempted first.
                    log.append(('r1_preempted', sim.time))
                    await sim.wait(20)
        except r0.Preempted:
            log.append(('r0_preempted', sim.time))

    async def preempt_r0():
        await sim.wait(3)
        # Priorities are compared per-resource (there is no global table).
        # This preempts r0 holder (priority 5); r1 holder priority (10) is irrelevant.
        with r0.autorelease():
            got = await r0.get(priority=1, preempt=True)
            assert got == 1
            await sim.wait(1)

    sim.schedule(0, nested_owner())
    sim.schedule(0, preempt_r0())
    sim.run(20)

    assert log == [('r0_preempted', 3)]
    assert r0.amount == 1
    assert r1.amount == 1
    print(f'nested preemptions: {log}')
    for probe in (r0_probe, r1_probe):
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
