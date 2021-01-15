# Copyright 2020 NXP Semiconductors
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
from dssim.simulation import DSSchedulable, DSComponent, sim


class MyComponent(DSComponent):
    @DSSchedulable
    def do_somethingA(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print('A0 Time:', self.sim.time)
        print('A0 Sleeping for 5 sec')
        yield from self.sim.wait(5)
        print('A1 Time:', self.sim.time)
        print('A1 Sleeping for 2 sec')
        yield from self.sim.wait(2)
        print('A2 Time:', self.sim.time)
        print('A2 Finish')

    @DSSchedulable
    def do_somethingB(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print('B0 Time:', self.sim.time)
        print('B0 Sleeping for 1 sec')
        yield from self.sim.wait(1)
        print('B1 Time:', self.sim.time)
        print('B1 Sleeping for 3 sec')
        yield from self.sim.wait(3)
        print('B2 Time:', self.sim.time)
        print('B2 Finish')

    @DSSchedulable
    def do_somethingC(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print('C0 Time:', self.sim.time)
        print('C0 Scheduling A in 2 sec')
        self.sim.schedule(2, self.do_somethingA())
        print('C1 Time:', self.sim.time)
        print('C1 Sleeping for 4 sec')
        yield from self.sim.wait(4)
        print('C2 Time:', self.sim.time)
        print('C2 Scheduling B in 2 sec')
        self.sim.schedule(2, self.do_somethingB())
        print('C3 Time:', self.sim.time)
        print('C3 Finish')

    @DSSchedulable
    def dummy(self, num):
        print('Dummy run with', num)

if __name__ == '__main__':
    obj0 = MyComponent(name='obj0')
    print('Scheduling C in 8 sec')
    sim.schedule(8, obj0.do_somethingC())
    print('Scheduling Dummy in 2 sec')
    sim.schedule(2, obj0.dummy(12))
    sim.run(20)
