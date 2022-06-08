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
from dssim.simulation import DSSchedulable, DSProcess, DSComponent, sim
import inspect

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.taskA = DSProcess(self.do_somethingA(), name=self.name+'.taskA')
        self.taskB = DSProcess(self.do_somethingB(), name=self.name+'.taskB')
        self.taskC = DSProcess(self.do_somethingC(), name=self.name+'.taskC')
        self.taskDummy = self.dummy(12)

    def do_somethingA(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print(self.taskA, '0 Time:', self.sim.time)
        print(self.taskA, '0 Sleeping for 5 sec')
        yield from self.sim.wait(5)
        print(self.taskA, '1 Time:', self.sim.time)
        print(self.taskA, '1 Sleeping for 2 sec')
        yield from self.sim.wait(2)
        print(self.taskA, '2 Time:', self.sim.time)
        print(self.taskA, '2 Finish')

    def do_somethingB(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print(self.taskB, '0 Time:', self.sim.time)
        print(self.taskB, '0 Sleeping for 1 sec')
        yield from self.sim.wait(1)
        print(self.taskB, '1 Time:', self.sim.time)
        print(self.taskB, '1 Sleeping for 3 sec')
        yield from self.sim.wait(3)
        print(self.taskB, '2 Time:', self.sim.time)
        print(self.taskB, '2 Finish')

    def do_somethingC(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print(self.taskC, '0 Time:', self.sim.time)
        print(self.taskC, '0 Scheduling', self.taskA, 'in 2 sec')
        self.sim.schedule(2, self.taskA)
        print(self.taskC, '0 Time:', self.sim.time)
        print(self.taskC, '0 Sleeping for 4 sec')
        yield from self.sim.wait(4)
        print(self.taskC, '1 Time:', self.sim.time)
        print(self.taskC, '1 Scheduling', self.taskB, 'in 2 sec')
        self.sim.schedule(2, self.taskB)
        print(self.taskC, '2 Time:', self.sim.time)
        print(self.taskC, '2 Finish')

    @DSSchedulable
    def dummy(self, num):
        print(self.taskDummy, '0 run with', num)
        print(self.taskDummy, '0 waiting for finishing all the tasks...')
        print(self.taskDummy, '0 waiting for', self.taskA, 'to finish...')
        yield from self.taskA.join()
        print(self.taskDummy, '1 waiting for', self.taskB, 'to finish...')
        yield from self.taskB.join()
        print(self.taskDummy, '2 waiting for', self.taskC, 'to finish...')
        yield from self.taskC.join()
        print(self.taskDummy, '3 all tasks finished')

if __name__ == '__main__':
    obj0 = MyComponent(name='obj0')
    print('Scheduling task', obj0.taskC, 'in 8 sec')
    sim.schedule(8, obj0.taskC)
    # The dummy task does not have customized name
    print('Scheduling task', obj0.taskDummy, 'in 2 sec')
    sim.schedule(2, obj0.taskDummy)
    sim.run(20)
    assert inspect.getgeneratorstate(obj0.taskDummy) == inspect.GEN_CLOSED
