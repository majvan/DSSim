# Copyright 2026- majvan (majvan@gmail.com)
#
# LiteLayer2 counterpart of examples/pubsub/trajectory.py.
from dssim import DSSimulation, LiteLayer2
import random

sim = DSSimulation(layer2=LiteLayer2)


# Capacity-1 token queues emulate occupied/free production stations.
c0 = sim.lite_queue(capacity=1)
i0 = sim.lite_queue(capacity=1)
c1 = sim.lite_queue(capacity=1)
c0.put_nowait(object())
i0.put_nowait(object())
c1.put_nowait(object())


def product():
    token = yield from c0.gget()
    yield from sim.gsleep(3)
    c0.put_nowait(token)

    token = yield from i0.gget()
    yield from sim.gsleep(15)
    i0.put_nowait(token)

    token = yield from c1.gget()
    yield from sim.gsleep(3)
    c1.put_nowait(token)


def generator():
    while True:
        sim.schedule(0, product())
        yield from sim.gsleep(random.uniform(5, 15))


sim.schedule(0, generator())
time, ev = sim.run(150)
assert 135 < time <= 150, f"Unexpected value of the time of last event in simulation: {time}"
assert 65 < ev <= 90, f"Unexpected number of events: {ev}"
