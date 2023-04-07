from dssim.simulation import DSComponent, DSCallback, DSSimulation, DSTrackableEvent
from dssim.pubsub import DSProducer
from dssim.cond import DSFilter as _f


class Board(DSComponent):
    def __init__(self, inputs, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inputs = inputs
        cond0 = (_f(lambda e:inputs[0] in e.producers) | _f(lambda e:inputs[1] in e.producers)) & (_f(lambda e:inputs[2] in e.producers) | _f(lambda e: inputs[3] in e.producers))
        self.rx0 = DSCallback(self.callback0, cond=cond0, name=self.name + '.rx0')
        for ep in inputs:
            ep.add_subscriber(self.rx0)
        
        cond1 = _f(lambda e:inputs[3] in e.producers)
        self.rx1 = DSCallback(self.callback1, cond=cond1, name=self.name + '.rx1')
        for ep in inputs:
            ep.add_subscriber(self.rx1)

        cond2 = _f(lambda e: 'Ahoy' == e.value) | _f(lambda e:inputs[2] in e.producers)
        self.rx2 = DSCallback(self.callback2, cond=cond2, name=self.name + '.rx2')
        for ep in inputs:
            ep.add_subscriber(self.rx2)
        self.log = []

    def callback0(self, e):
        print(self.sim.time, 'Callback 0 called:', e)
        events = list(te.value for te in e.values())
        self.log.append((self.sim.time, 'c0', events))
        if len(events) < 4:
            return True  # If not all events were signaled, consume the event
        return False  # Else do not consume the event - no one else will get this event

    def callback1(self, e):
        print(self.sim.time, 'Callback 1 called:', e)
        events = [e.value,]
        self.log.append((self.sim.time, 'c1', events))
        return True  # Consume the event

    def callback2(self, e):
        print(self.sim.time, 'Callback 2 called:', e)
        events = list(te.value for te in e.values())
        self.log.append((self.sim.time, 'c2', events))
        return True  # Consume the event

sim = DSSimulation()
signals = [DSProducer(name=f'signal{i}', sim=sim) for i in range (4)]
m = Board(signals, name='motherboard0', sim=sim)
signals[0].schedule_event(1, DSTrackableEvent('Hi'))
signals[1].schedule_event(2, DSTrackableEvent('Hello'))
signals[3].schedule_event(3, DSTrackableEvent('Ahoy'))
signals[2].schedule_event(4, DSTrackableEvent('Bye'))
signals[3].schedule_event(5, DSTrackableEvent('Bye'))

sim.run(10)
assert m.log == [
    (3, 'c0', ['Hi', 'Hello', 'Ahoy']), 
    (4, 'c0', ['Hi', 'Hello', 'Bye', 'Ahoy']), 
    (4, 'c2', ['Bye']), 
    (5, 'c0', ['Hi', 'Hello', 'Bye', 'Ahoy']), 
    (5, 'c1', ['Bye'])
    ]