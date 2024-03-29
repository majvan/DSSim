# Copyright 2022- majvan (majvan@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from dssim import DSProcess, DSComponent, DSSimulation, DSProducer

class Switch(DSComponent):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = 0
        for i in range(3):
            self.sim.process(self.process(i), name=f"{self.name}.take{i}").schedule(0)
        self.producer = self.sim.producer(name=f"{self.name}.feed")
        self.sim.process(self.feeder(), name=f"{self.name}.feedprocess").schedule(0)

    def feeder(self):
        yield from self.sim.gwait(3)
        print(f'Feeder feeding with char a')
        retval = self.producer.send('a')
        assert self.counter == 3
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char b')
        retval = self.producer.send('b')
        assert self.counter == 4
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char c')
        self.producer.send('c')
        assert self.counter == 6
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char d')
        self.producer.send('d')
        assert self.counter == 7
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char d')
        self.producer.send('d')
        assert self.counter == 8
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char e')
        self.producer.send('e')
        assert self.counter == 9
        yield from self.sim.gwait(1)
        print(f'Feeder feeding with char f')
        self.producer.send('f')
        assert self.counter == 9

    def process(self, nr):
        with self.sim.extend_cond(cond=lambda e:True):
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
            data = yield from self.sim.gwait(cond=lambda e:True)
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 0")
            # we decided to return 0 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event
            data = yield from self.sim.gwait(cond=lambda e:True, val=0)  
            self.counter += 1
            print(f"Process {nr} was given feed data {data}")
            print(f"Process {nr} returning back 1 - this should consume the event")
            # we decided to return 1 to the feeder as a reply to the ALREADY PROCESSED event and to wait for a next event            
            data = yield from self.sim.gwait(cond=lambda e:True, val=1)
            self.counter += 1
            print(f"Process {nr} returning with {nr}")
        return nr

if __name__ == '__main__':
    sim = DSSimulation()
    print('First switch having consumers implemented with yield <literal>')
    s = Switch(name="yield_switch", sim=sim)
    sim.run(10)
    # The second switch is functionally the same as the first one, but sim.wait() gives you more flexibility on filtering
    print()
    print('The second switch having consumers implemented with yield from sim.gwait()')
    s = Switch2(name="wait_switch", sim=sim)
    sim.run(20)
