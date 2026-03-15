# Copyright 2026- majvan (majvan@gmail.com)
#
# LiteLayer2 counterpart of examples/pubsub/DSPriorityResource pubsub.py.
#
# Uses DSLitePriorityResource (priority + optional preemption) available in
# dssim.lite.components.literesource via sim.priority_resource(...).
from dssim import DSSimulation, LiteLayer2
from dssim.lite import DSResourcePreempted


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


def run_lite_non_preemptive():
    sim = DSSimulation(layer2=LiteLayer2)
    res = sim.priority_resource(amount=1, capacity=1, preemptive=False, name='clerks')
    starts = []

    def customer(name, arrival, priority, service):
        yield from sim.gsleep(arrival)
        got = yield from res.gget(priority=priority)
        assert got == 1
        starts.append((name, sim.time))
        yield from sim.gsleep(service)
        res.put_nowait()

    for job in NON_PREEMPTIVE_JOBS:
        sim.schedule(0, customer(*job))

    sim.run(30)
    return starts


def run_lite_preemptive():
    sim = DSSimulation(layer2=LiteLayer2)
    resource = sim.priority_resource(amount=1, capacity=1, preemptive=True, name='machine')
    log = []

    def job(name, arrival, prio, service):
        yield from sim.gsleep(arrival)
        remaining = service
        while remaining > 0:
            with resource.autorelease():
                got = yield from resource.gget(priority=prio, preempt=True)
                assert got == 1
                yield from sim.gsleep(ACQUIRE_SETTLE)
                start = sim.time
                log.append(('start', name, tstamp(sim.time)))
                try:
                    yield from sim.gsleep(remaining)
                    remaining = 0
                    log.append(('finish', name, tstamp(sim.time)))
                except DSResourcePreempted:
                    remaining -= sim.time - start
                    log.append(('preempted', name, tstamp(sim.time), tstamp(remaining)))

    for item in PREEMPTIVE_JOBS:
        sim.schedule(0, job(*item))
    sim.run(30)
    return log


if __name__ == '__main__':
    print('Demo 1: DSLitePriorityResource (non-preemptive) — DSSim Lite')
    lite_starts = run_lite_non_preemptive()
    print('Lite starts:', lite_starts)
    assert lite_starts == [('low', 0), ('high', 4), ('mid', 5)]
    print('Non-preemptive parity OK.')

    print('\nDemo 2: Lite preemptive semantics (with interruption) — DSSim Lite')
    lite_log = run_lite_preemptive()
    print('Lite log:', lite_log)
    assert lite_log == [
        ('start', 'low', 0.001),
        ('preempted', 'low', 3.0, 7.001),
        ('start', 'high', 3.001),
        ('finish', 'high', 5.001),
        ('start', 'low', 5.002),
        ('finish', 'low', 12.003),
    ]
    lite_times = [item[2] for item in lite_log]
    assert len(lite_times) == len(set(lite_times)), 'Lite preemptive demo should have unique event times.'
    print('Preemptive parity OK.')
