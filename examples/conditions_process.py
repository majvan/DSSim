from dssim.simulation import DSProcess, DSSchedulable, DSSimulation
from dssim.cond import DSFilter as _f

@DSSchedulable
def pusher(name, where_to_push):
    sim.send(where_to_push, f'signal from pusher {name}')

def process_with_no_external_events():
    yield from sim.gwait(1)
    yield from sim.gwait(2)
    return 'Hello from introvert'

def process_with_external_events():
    event = yield from sim.gwait(cond=lambda c:True)
    return f'Hello from extrovert, last event I had was "{event}"'

def main():
    # NOT WORKING
    # proc = DSProcess(process_with_no_external_events())
    # ret = yield from proc  # yield from process should be avoided because it has side efects like keeping an extra "finished" event after finish
    # print(sim.time, ret)

    proc = DSProcess(process_with_no_external_events())
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=_f(proc))
    print(sim.time, ret)
    assert sim.time == 3
    assert ret == 'Hello from introvert'

    proc = sim.schedule(0, DSProcess(process_with_no_external_events()))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=_f(proc))  # this will work
    print(sim.time, ret)
    assert sim.time == 6
    assert ret == 'Hello from introvert'

    proc = sim.schedule(0, DSProcess(process_with_external_events()))
    sim.schedule(4, pusher('first', proc))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=_f(proc))  # this will work despite the fact that the last push was not scheduled by our process
    print(sim.time, ret)
    assert sim.time == 10
    assert ret == 'Hello from extrovert, last event I had was "signal from pusher first"'

    coro = sim.schedule(0, process_with_external_events())
    filt = _f(coro)
    proc = filt.get_process()
    sim.schedule(5, pusher('second', proc))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=filt)
    print(sim.time, ret)
    assert sim.time == 15
    assert ret == 'Hello from extrovert, last event I had was "signal from pusher second"'

    # proc = process_with_external_events()
    # sim.schedule(3, pusher('second', proc))
    # ret = yield from sim.gwait(cond=_f(proc))  # this will not work because the _f() converts to a DSProcess and pusher is pushing generator
    # print(sim.time, ret)

    filt = _f(process_with_external_events())
    proc = filt.get_process()
    sim.schedule(6, pusher('third', proc))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=filt)  # this will work
    print(sim.time, ret)
    assert sim.time == 21
    assert ret == 'Hello from extrovert, last event I had was "signal from pusher third"'

    filt = _f(DSProcess(process_with_external_events()))
    proc = filt.get_process()
    sim.schedule(7, pusher('forth', proc))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=filt)  # this will work
    print(sim.time, ret)
    assert sim.time == 28
    assert ret == 'Hello from extrovert, last event I had was "signal from pusher forth"'

    proc = sim.schedule(0, DSProcess(process_with_external_events()))
    filt = _f(proc)
    assert proc == filt.get_process()
    sim.schedule(8, pusher('fifth', proc))
    with sim.observe_pre(proc):
        ret = yield from sim.gwait(cond=filt)  # this will work
    print(sim.time, ret)
    assert sim.time == 36
    assert ret == 'Hello from extrovert, last event I had was "signal from pusher fifth"'


if __name__ == '__main__':
    sim = DSSimulation()
    sim.schedule(0, main())
    retval = sim.run(100)
    assert retval == (36, 24)
