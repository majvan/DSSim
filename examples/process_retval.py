from dssim.simulation import DSProcess, DSComponent, sim
from dssim.pubsub import DSProducer

class Switch(DSComponent):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = 0
        for i in range(3):
            p = DSProcess(self.process(i), name=f"{self.name}.take{i}")
            self.sim.schedule(0, p)
        self.producer = DSProducer(name=f"{self.name}.feed")
        self.sim.schedule(0, DSProcess(self.feeder(), name=f"{self.name}.feedprocess"))

    def feeder(self):
        yield from self.sim.wait(3)
        print(f'Feeder feeding with char a')
        self.producer.signal(char='a')
        assert self.counter == 3
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char b')
        self.producer.signal(char='b')
        assert self.counter == 4
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char c')
        self.producer.signal(char='c')
        assert self.counter == 6
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char d')
        self.producer.signal(char='d')
        assert self.counter == 7
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char d')
        self.producer.signal(char='d')
        assert self.counter == 8
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char e')
        self.producer.signal(char='e')
        assert self.counter == 9
        yield from self.sim.wait(1)
        print(f'Feeder feeding with char f')
        self.producer.signal(char='f')
        assert self.counter == 9

    def process(self, nr):
        with self.sim.consume(self.producer):
            data = yield 0  # wait for any event
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 0")
            # we decided to return 0 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event
            data = yield 0
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 1 - this should consume the event")
            # we decided to return 1 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event            
            data = yield 1
            self.counter += 1
            print(f"Process {nr} returning with {nr}")
        return nr


class Switch2(Switch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process(self, nr):
        with self.sim.consume(self.producer):
            # wait for any event
            data = yield from self.sim.wait(cond=lambda e:True)
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 0")
            # we decided to return 0 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event
            data = yield from self.sim.wait(cond=lambda e:True, val=0)  
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 1 - this should consume the event")
            # we decided to return 1 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event            
            data = yield from self.sim.wait(cond=lambda e:True, val=1)
            self.counter += 1
            print(f"Process {nr} returning with {nr}")
        return nr

print('First switch having consumers implemented with yield <literal>')
s = Switch(name="yield_switch")
sim.run(10)
# The second switch is functionally the same as the first one, but sim.wait() gives you more flexibility on filtering
print()
print('The second switch having consumers implemented with yield from sim.wait()')
s = Switch2(name="wait_switch")
sim.run(20)
