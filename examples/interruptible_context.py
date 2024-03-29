# Copyright 2023- majvan (majvan@gmail.com)
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
'''
An example showing the possibilities to interrupt context in dssim.
'''
from dssim import DSSimulation, DSComponent
from dssim import DSProducer, DSTransformation, DSProcess

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ep = self.sim.producer(name=self.name + '.ep')

    async def process0(self):
        ''' The process listens on the self.ep producer in a way that all the events
        from the producer are transformed to the ValueError(e).
        The exception interrupts the context.
        '''
        print('Process0')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        try:
            ep = DSTransformation(self.ep, lambda e: ValueError(e))
            with self.sim.observe_pre(ep) as cm:
                print(self.sim.time, 'Waiting...')
                event = await self.sim.wait(100)  # No signal should stop this, only Exception
                assert False, 'This should not be executed because a signal from main creates exception'
        except Exception as e:
            assert isinstance(e, ValueError)
            assert str(e) == 'Hello'
        assert self.sim.time == t + 10
        print(self.sim.time, 'Interrupted.')
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert sum(ep.subs['pre'].d.values()) == 0
        assert cond_stack == [None,]

    async def process1(self):
        ''' The same as previous, but transforming into DSTimeout
        '''
        print('Process1')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        with self.sim.timeout(10) as cm:
            print(self.sim.time, 'Waiting...')
            event = await self.sim.wait(100)  # No signal should stop this, only Exception
            assert False, 'This should not be executed because a signal from main creates exception'
        assert self.sim.time == t + 10
        assert cm.interrupted()
        print(self.sim.time, 'Interrupted.')
        assert cond_stack == [None,]

    async def process2(self):
        ''' Two timeouts cascading. Showing how they are interrupted.
        '''
        print('Process2')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        with self.sim.timeout(10) as cm0:
            with self.sim.timeout(20) as cm1:
                print(self.sim.time, 'Waiting...')
                event = await self.sim.wait(100)  # No signal should stop this, only Exception
                assert False, 'This should not be executed because a signal from main creates exception0'
            assert False, 'This should not be executed because a signal from main creates exception1'
        assert self.sim.time == t + 10
        assert not cm1.interrupted()
        assert cm0.interrupted()
        print(self.sim.time, 'Interrupted.')
        assert cond_stack == [None,]

    async def process3(self):
        ''' The process has extended condition, so the wait can be signalled also with 'Hi'
        '''
        print('Process3')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        event = None
        with self.sim.observe_pre(self.ep) as cm:
            with self.sim.extend_cond(cond='Hi'):
                print(self.sim.time, 'Waiting 100')
                event = await self.sim.wait(100)  # No signal should stop this, only Exception
                assert True, 'This line has to be run.'
        assert event == 'Hi'
        assert self.sim.time == t + 10
        print(self.sim.time, 'Signaled.')
        assert cond_stack == [None,]

    async def process4(self):
        ''' Similar to previous, but with interruptible. Interruptible condition however breaks the context.
        '''
        print('Process4')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        event = None
        with self.sim.observe_pre(self.ep):
            with self.sim.interruptible(cond='Hi') as cm:
                    print(self.sim.time, 'Waiting 100')
                    event = await self.sim.wait(100)  # No signal should stop this, only Exception
                    assert False, 'This line should not be executed.'
        assert self.sim.time == t + 10
        assert cm.interrupted()
        print(self.sim.time, 'Interrupted.')
        assert cm.value == 'Hi'
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert cond_stack == [None,]

    async def process5(self):
        ''' The same code as previous. This time the timeout will be taken.
        '''
        print('Process5')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        event = None
        with self.sim.observe_pre(self.ep):
            with self.sim.timeout(20) as cm0:
                with self.sim.interruptible(cond='Hi') as cm1:
                    print(self.sim.time, 'Waiting 100')
                    event = await self.sim.wait(100)  # No signal should stop this, only Exception
        assert event == None
        assert self.sim.time == t + 20
        assert not cm1.interrupted()
        assert cm0.interrupted()
        print(self.sim.time, 'Interrupted.')
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert cond_stack == [None,]

    async def process6(self):
        ''' The same code as previous. This time the timeout will be taken.
        '''
        print('Process6')
        cond_stack = self.sim.pid.get_cond().conds
        assert cond_stack == [None,]
        t = self.sim.time
        event = None
        assert len(cond_stack) == 1
        with self.sim.observe_pre(DSTransformation(self.ep, lambda e: e + ' transformed')):
            with self.sim.timeout(20) as cm0:
                with self.sim.interruptible(cond='Bye transformed') as cm1:
                    print(self.sim.time, 'Waiting 100')
                    event = await self.sim.wait(100)  # No signal should stop this, only Exception
        assert event == None
        assert self.sim.time == t + 15
        assert cm1.interrupted()
        assert not cm0.interrupted()
        print(self.sim.time, 'Interrupted.')
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert cond_stack == [None,]


async def main(mc):
    sim.schedule(0, mc.process0())
    await sim.wait(10)
    print(sim.time, 'Sending Hello')
    mc.ep.signal('Hello')

    sim.schedule(0, mc.process1())
    await sim.wait(20)

    p = DSProcess(mc.process2(), sim=sim).schedule(0)
    await p

    sim.schedule(0, mc.process3())
    await sim.wait(5)
    print(sim.time, 'Sending Hello')
    mc.ep.signal('Hello')
    await sim.wait(5)
    print(sim.time, 'Sending Hi')
    mc.ep.signal('Hi')

    sim.schedule(0, mc.process4())
    await sim.wait(5)
    print(sim.time, 'Sending Hello')
    mc.ep.signal('Hello')
    await sim.wait(5)
    print(sim.time, 'Sending Hi')
    mc.ep.signal('Hi')

    sim.schedule(0, mc.process5())
    await sim.wait(5)
    print(sim.time, 'Sending Hello')
    mc.ep.signal('Hello')
    await sim.wait(20)
    print(sim.time, 'Sending Hi')
    mc.ep.signal('Hi')

    sim.schedule(0, mc.process6())
    await sim.wait(5)
    print(sim.time, 'Sending Hello')
    mc.ep.signal('Hello')
    await sim.wait(5)
    print(sim.time, 'Sending Hi')
    mc.ep.signal('Hi')
    await sim.wait(5)
    print(sim.time, 'Sending Bye')
    mc.ep.signal('Bye')

    
sim = DSSimulation()
mc = MyComponent(sim=sim)
sim.schedule(0, main(mc))
sim.run()
