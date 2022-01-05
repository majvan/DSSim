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

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.taskA = DSProcess(self.do_somethingA(), name=self.name+'.taskA')
        self.taskB = DSProcess(self.do_somethingB(), name=self.name+'.taskB')
        self.taskC = DSProcess(self.do_somethingC(), name=self.name+'.taskC')
        self.taskDummy = self.dummy(12)

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

    def do_somethingC(self):
        # The following will be run in a time t=10 sec (see below schedule_future)
        print('C0 Time:', self.sim.time)
        print('C0 Scheduling', self.taskA, 'in 2 sec')
        self.sim.schedule(2, self.taskA)
        print('C1 Time:', self.sim.time)
        print('C1 Sleeping for 4 sec')
        yield from self.sim.wait(4)
        print('C2 Time:', self.sim.time)
        print('C2 Scheduling', self.taskB, 'in 2 sec')
        self.sim.schedule(2, self.taskB)
        print('C3 Time:', self.sim.time)
        print('C3 Finish')

    @DSSchedulable
    def dummy(self, num):
        print('Dummy run with', num)
        print('Dummy waiting for finishing all the tasks')
        print('Waiting for', self.taskA, 'to finish...')
        yield from self.taskA.join()
        print('Waiting for', self.taskB, 'to finish...')
        yield from self.taskB.join()
        print('Waiting for', self.taskC, 'to finish...')
        yield from self.taskC.join()
        print('All tasks finished')

if __name__ == '__main__':
    obj0 = MyComponent(name='obj0')
    print('Scheduling task', obj0.taskC, 'in 8 sec')
    sim.schedule(8, obj0.taskC)
    # The dummy task does not have customized name
    print('Scheduling task', obj0.taskDummy, 'in 2 sec')
    sim.schedule(2, obj0.taskDummy)
    sim.run(20)
