#!/usr/bin/env python3
# Copyright 2026- majvan (majvan@gmail.com)
'''
Nested ownership on two preemptive priority resources in LiteLayer2.

Demonstrates resource-specific preemption catches:
- the process holds r0, then nested holds r1
- another process preempts only r0
- outer except r0.Preempted catches it
- inner except r1.Preempted is not triggered in this scenario
'''

from dssim import DSSimulation, LiteLayer2


def main() -> None:
    sim = DSSimulation(layer2=LiteLayer2)
    r0 = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='r0')
    r1 = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='r1')
    log = []

    def nested_owner():
        try:
            with r0.autorelease():
                got0 = yield from r0.gget(priority=5, preempt=True)
                assert got0 == 1
                try:
                    with r1.autorelease():
                        got1 = yield from r1.gget(priority=10, preempt=True)
                        assert got1 == 1
                        yield from sim.gwait(20)
                except r1.Preempted:
                    # This does not happen in this scenario; r0 is preempted first.
                    log.append(('r1_preempted', sim.time))
                    yield from sim.gwait(20)
        except r0.Preempted:
            log.append(('r0_preempted', sim.time))

    def preempt_r0():
        yield from sim.gwait(3)
        # Priorities are compared per-resource (there is no global table).
        # This preempts r0 holder (priority 5); r1 holder priority (10) is irrelevant.
        with r0.autorelease():
            got = yield from r0.gget(priority=1, preempt=True)
            assert got == 1
            yield from sim.gwait(1)

    sim.schedule(0, nested_owner())
    sim.schedule(0, preempt_r0())
    sim.run(20)

    assert log == [('r0_preempted', 3)]
    assert r0.amount == 1
    assert r1.amount == 1
    print(f'nested preemptions: {log}')


if __name__ == '__main__':
    main()
