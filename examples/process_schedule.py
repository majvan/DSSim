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
from dssim import DSProcess, DSComponent, DSSimulation
import inspect

class MyComponent(DSComponent):
    def __init__(self, dummy_selection, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.taskA = DSProcess(self.do_somethingA(), name=self.name+'.taskA', sim=self.sim)
        self.taskB = DSProcess(self.do_somethingB(), name=self.name+'.taskB', sim=self.sim)
        self.taskC = DSProcess(self.do_somethingC(), name=self.name+'.taskC', sim=self.sim)
        if dummy_selection == 'gjoin':
            self.taskDummy = self.dummy_gjoin(dummy_selection)
        elif dummy_selection == 'join':
            self.taskDummy = self.dummy_join(dummy_selection)
        else:
            self.taskDummy = self.dummy(dummy_selection)

    def do_somethingA(self):
        assert self.sim.time == 10
        print(self.sim.time, self.taskA, '0 Sleeping for 5 sec')
        yield from self.sim.gwait(5)
        assert self.sim.time == 15
        print(self.sim.time, self.taskA, '1 Sleeping for 2 sec')
        yield from self.sim.gwait(2)
        assert self.sim.time == 17
        print(self.sim.time, self.taskA, '2 Finish')

    def do_somethingB(self):
        assert self.sim.time == 14
        print(self.sim.time, self.taskB, '0 Sleeping for 1 sec')
        yield from self.sim.gwait(1)
        assert self.sim.time == 15
        print(self.sim.time, self.taskB, '1 Sleeping for 3 sec')
        yield from self.sim.gwait(3)
        assert self.sim.time == 18
        print(self.sim.time, self.taskB, '2 Finish')

    def do_somethingC(self):
        assert self.sim.time == 8
        print(self.sim.time, self.taskC, '0 Scheduling', self.taskA, 'in 2 sec')
        self.sim.schedule(2, self.taskA)
        assert self.sim.time == 8
        print(self.sim.time, self.taskC, '0 Sleeping for 4 sec')
        yield from self.sim.gwait(4)
        assert self.sim.time == 12
        print(self.sim.time, self.taskC, '1 Scheduling', self.taskB, 'in 2 sec')
        self.sim.schedule(2, self.taskB)
        assert self.sim.time == 12
        print(self.sim.time, self.taskC, '2 Finish')

    def dummy_gjoin(self, name):
        print(self.sim.time, self.taskDummy, '0 run with', name)
        print(self.sim.time, self.taskDummy, '0 waiting for', self.taskA, 'to finish...')
        yield from self.taskA.gwait()
        print(self.sim.time, self.taskDummy, '1 waiting for', self.taskB, 'to finish...')
        yield from self.taskB.gwait()
        print(self.sim.time, self.taskDummy, '2 waiting for', self.taskC, 'to finish...')
        yield from self.taskC.gwait()
        print(self.sim.time, self.taskDummy, '3 all tasks finished')

    async def dummy_join(self, name):
        print(self.sim.time, self.taskDummy, '0 run with', name)
        print(self.sim.time, self.taskDummy, '0 waiting for', self.taskA, 'to finish...')
        await self.taskA
        print(self.sim.time, self.taskDummy, '1 waiting for', self.taskB, 'to finish...')
        await self.taskB.wait()
        print(self.sim.time, self.taskDummy, '2 waiting for', self.taskC, 'to finish...')
        await self.taskC.wait()
        print(self.sim.time, self.taskDummy, '3 all tasks finished')

    async def dummy(self, name):
        print(self.sim.time, self.taskDummy, '0 run with', name)
        print(self.sim.time, self.taskDummy, '0 waiting for', self.taskA, 'to finish...')
        await self.taskA
        assert self.sim.time == 17
        print(self.sim.time, self.taskDummy, '1 waiting for', self.taskB, 'to finish...')
        await self.taskB.wait()
        assert self.sim.time == 18
        print(self.sim.time, self.taskDummy, '2 waiting for', self.taskC, 'to finish...')
        await self.taskC.wait()
        assert self.sim.time == 18
        print(self.sim.time, self.taskDummy, '3 all tasks finished')


if __name__ == '__main__':
    sim = DSSimulation()
    # Run 3 components in parallel. Each components uses dummy waiting task in different way.
    obj0 = MyComponent('gjoin', name='ComponentGJoin', sim=sim)
    obj1 = MyComponent('join', name='ComponentJoin', sim=sim)
    obj2 = MyComponent('', name='Component', sim=sim)
    # Schedule them process (taskC)
    for obj in (obj0, obj1, obj2):
        print('Scheduling task', obj.taskC, 'in 8 sec')
        sim.schedule(8, obj.taskC)
    # Schedule them taskDummy
    for obj in (obj0, obj1, obj2):
        print('Scheduling task', obj.taskDummy, 'in 2 sec')
        sim.schedule(2, obj.taskDummy)

    sim.run(20)
    assert inspect.getgeneratorstate(obj0.taskDummy) == inspect.GEN_CLOSED
    assert inspect.getcoroutinestate(obj1.taskDummy) == inspect.CORO_CLOSED
    assert inspect.getcoroutinestate(obj2.taskDummy) == inspect.CORO_CLOSED
