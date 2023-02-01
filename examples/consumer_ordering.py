from dssim.simulation import DSComponent, DSSimulation, DSProcess
from dssim.pubsub import NotifierDict, NotifierRoundRobin, NotifierPriority, DSProducer

class SingleProducerMultipleConsumers(DSComponent):
    def __init__(self, notifier_method, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.p = DSProducer(name=f'{self.name}.generator', notifier=notifier_method, sim=self.sim)
        self.sim.schedule(1, self.producer())
        for order in range(6):
            DSProcess(self.consumer(order), name=self.name+f'.consumer{order}', sim=self.sim).schedule(0)
        self.log = []

    def producer(self):
        while True:
            self.p.signal('hello from producer')
            yield from self.sim.wait(1)

    def consumer(self, order):
        with sim.consume(self.p, priority=order % 3):
            while True:
                data = yield from self.sim.wait(cond=lambda e:True, val=(order == 2))
                self.log.append((self.sim.time, order))
                print(f'{self.sim.time} Consumer {order} notified with {data}')

sim = DSSimulation(name='dssim0')
system = SingleProducerMultipleConsumers(NotifierDict, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)]

sim = DSSimulation(name='dssim1')
system = SingleProducerMultipleConsumers(NotifierRoundRobin, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 1), (1, 2), (2, 3), (2, 4), (2, 5), (2, 0), (2, 1), (2, 2), (3, 3), (3, 4), (3, 5), (3, 0), (3, 1), (3, 2)]

sim = DSSimulation(name='dssim2')
system = SingleProducerMultipleConsumers(NotifierPriority, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 3), (1, 1), (1, 4), (1, 2), (2, 0), (2, 3), (2, 1), (2, 4), (2, 2), (3, 0), (3, 3), (3, 1), (3, 4), (3, 2)]
