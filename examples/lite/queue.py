# Copyright 2026- majvan (majvan@gmail.com)
#
# LiteLayer2 counterpart of examples/pubsub/queue.py.
from dssim import DSSimulation, LiteLayer2
import inspect


def do_somethingA():
    print('A0 Time:', sim.time)
    print('A0 Sleeping for 4 sec')
    yield from sim.gsleep(4)
    print('A1 Time:', sim.time)
    print('A1 Messaging B')
    q_ab.put_nowait('Message from A1')
    print('A1 Sleeping for 1 sec')
    yield from sim.gsleep(1)
    print('A2 Time:', sim.time)
    print('A2 Messaging B')
    q_ab.put_nowait('Message from A2')
    print('A2 Waiting for message from B')
    msg = yield from q_ba.gget()
    print('A3 Time:', sim.time)
    print('A3 Got message from B', msg)
    print('A3 Waiting for message from B')
    msg = yield from q_ba.gget()
    print('A4 Time:', sim.time)
    print('A4 Got message from B', msg)
    print('A4 Finish')


def do_somethingB():
    print('B0 Time:', sim.time)
    print('B0 Waiting for message from A')
    msg = yield from q_ab.gget()
    print('B1 Time:', sim.time)
    print('B1 Got message from A', msg)
    print('B1 Waiting for message from A')
    msg = yield from q_ab.gget()
    print('B2 Time:', sim.time)
    print('B2 Got message from A', msg)
    print('B2 Sleeping for 5 sec')
    yield from sim.gsleep(5)
    print('B3 Time:', sim.time)
    print('B3 Messaging A')
    q_ba.put_nowait('Message from B3')
    print('B3 Sleeping for 3 sec')
    yield from sim.gsleep(3)
    print('B4 Time:', sim.time)
    print('B4 Messaging A')
    q_ba.put_nowait('Message from B4')
    print('B4 Sleeping for 3 sec')
    yield from sim.gsleep(3)
    print('B5 Time:', sim.time)
    print('B5 Finish')


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    q_ab, q_ba = sim.lite_queue(), sim.lite_queue()
    process_a, process_b = do_somethingA(), do_somethingB()
    sim.schedule(0, process_a)
    sim.schedule(0, process_b)
    sim.run(20)

    assert inspect.getgeneratorstate(process_a) == inspect.GEN_CLOSED
    assert inspect.getgeneratorstate(process_b) == inspect.GEN_CLOSED
