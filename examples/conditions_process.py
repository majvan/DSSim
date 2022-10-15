from dssim.simulation import DSProcess, DSSchedulable, DSSimulation
from dssim.cond import DSFilter as _f

@DSSchedulable
def pusher(name, what_to_push):
    sim.signal(what_to_push, info=f'signal from pusher {name}')

def process_with_no_external_events():
    yield from sim.wait(1)
    yield from sim.wait(2)
    return 'Hello from introvert'

def process_with_external_events():
    event = yield from sim.wait(cond=lambda c:True)
    return f'Hello from extrovert, last event I had was "{event}"'

def main():
    # NOT WORKING
    # proc = DSProcess(process_with_no_external_events())
    # ret = yield from proc  # yield from process should be avoided because it has side efects like keeping an extra "finished" event after finish
    # print(sim.time, ret)

    proc = DSProcess(process_with_no_external_events())
    ret = yield from sim.wait(cond=_f(proc))
    print(sim.time, ret)

    proc = sim.schedule(0, DSProcess(process_with_no_external_events()))
    ret = yield from sim.wait(cond=_f(proc))  # this will work
    print(sim.time, ret)

    proc = sim.schedule(0, DSProcess(process_with_external_events()))
    sim.schedule(4, pusher('first', proc))
    ret = yield from sim.wait(cond=_f(proc))  # this will work despite the fact that the last push was not done by time_process
    print(sim.time, ret)

    proc = sim.schedule(0, process_with_external_events())
    filt = _f(proc)
    sim.schedule(5, pusher('second', filt.get_process()))
    ret = yield from sim.wait(cond=filt)  # this will raise a ValueError because generator is already started
    print(sim.time, ret)

    # proc = process_with_external_events()
    # sim.schedule(3, pusher('second', proc))
    # ret = yield from sim.wait(cond=_f(proc))  # this will not work because the _f() converts to a DSProcess and pusher is pushing generator
    # print(sim.time, ret)

    filt = _f(process_with_external_events())
    sim.schedule(6, pusher('third', filt.get_process()))
    ret = yield from sim.wait(cond=filt)  # this will work
    print(sim.time, ret)

    filt = _f(DSProcess(process_with_external_events()))
    sim.schedule(7, pusher('forth', filt.get_process()))
    ret = yield from sim.wait(cond=filt)  # this will work
    print(sim.time, ret)

    proc = sim.schedule(0, DSProcess(process_with_external_events()))
    filt = _f(proc)
    assert proc == filt.get_process()
    sim.schedule(8, pusher('fifth', filt.get_process()))
    ret = yield from sim.wait(cond=filt)  # this will work
    print(sim.time, ret)


if __name__ == '__main__':
    sim = DSSimulation()
    sim.schedule(0, main())
    sim.run(100)
