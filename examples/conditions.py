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
from dssim import DSSimulation, DSProcess, DSFuture, DSFilter as f


def return_greeting_after(time, greeting):
    yield from sim.gwait(time)
    return greeting

def signal_future_after(time, future, value='Signal!'):
    yield from sim.gwait(time)
    future.finish(value)

async def demo_filtering0():
    ''' Testing one future '''
    # Test await future
    time = sim.time
    fut = DSFuture()
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await fut
    assert ret == fut
    assert fut.value == 'Signal!'
    assert sim.time == time + 2

    # Test future.wait()
    time = sim.time
    fut = DSFuture()
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await fut.wait()
    assert ret == fut
    assert fut.value == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    fut = DSFuture()
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await fut.wait(1)
    assert ret is None
    assert sim.time == time + 1

    # Test sim.wait(future)
    time = sim.time
    fut = DSFuture()
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    with sim.observe_post(fut):
        ret = await sim.wait(cond=fut)
    assert ret == fut
    assert fut.value == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    fut = DSFuture()
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    with sim.observe_post(fut):
        ret = await sim.wait(1, cond=fut)
    assert ret == None
    assert sim.time == time + 1

    # Test await cond
    time = sim.time
    fut = DSFuture()
    cond = f(fut)
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await cond
    assert ret == 'Signal!'
    assert sim.time == time + 2

    # Test await cond.wait()
    time = sim.time
    fut = DSFuture()
    cond = f(fut)
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await cond.wait()
    assert ret == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    fut = DSFuture()
    cond = f(fut)
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    ret = await cond.wait(1)
    assert ret is None
    assert sim.time == time + 1

    # Test await sim.wait(cond)
    time = sim.time
    fut = DSFuture()
    cond = f(fut)
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    with sim.observe_pre(fut):
        ret = await sim.wait(cond=cond)
    assert ret == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    fut = DSFuture()
    cond = f(fut)
    DSProcess(signal_future_after(2, fut), sim=sim).schedule(0)
    with sim.observe_pre(fut):
        ret = await sim.wait(1, cond=cond)
    assert ret == None
    assert sim.time == time + 1

async def demo_filtering1():
    ''' Testing f(future) | f(future) '''
    # Test await cond
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    ret = await cond
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    # Test await cond.wait
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    ret = await cond.wait()
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    ret = await cond.wait(1)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

    # Test await sim.wait
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    cond = (cond0 | cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(cond=cond)
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    with sim.observe_pre(cond):
        ret = await sim.wait(1, cond=cond)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

async def demo_filtering2():
    ''' Testing f(future) & f(future) '''
    # Test await cond
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 & cond1
    ret = await cond
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    # Test await cond.wait
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 & cond1
    ret = await cond.wait()
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 & cond1
    ret = await cond.wait(1)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

    # Test await sim.wait
    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 | cond1
    cond = (cond0 & cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(cond=cond)
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    fut0 = DSFuture()
    DSProcess(signal_future_after(10, fut0, value='hi'), sim=sim).schedule(0)
    fut1 = DSFuture()
    DSProcess(signal_future_after(5, fut1, value='hello'), sim=sim).schedule(0)
    cond0, cond1 = f(fut0), f(fut1)
    cond = cond0 & cond1
    with sim.observe_pre(cond):
        ret = await sim.wait(1, cond=cond)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1


async def demo_filtering3():
    ''' Testing one process '''
    # Test await process
    time = sim.time
    fut = DSProcess(return_greeting_after(2, 'Signal!'), sim=sim).schedule(0)
    ret = await fut
    assert ret == fut
    assert fut.value == 'Signal!'
    assert sim.time == time + 2

    # Test sim.wait(future)
    time = sim.time
    fut = DSProcess(return_greeting_after(2, 'Signal!'), sim=sim).schedule(0)
    with sim.observe_pre(fut):
        ret = await sim.wait(cond=fut)
    assert ret == fut
    assert fut.value == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    fut = DSProcess(return_greeting_after(2, 'Signal!'), sim=sim).schedule(0)
    with sim.observe_pre(fut):
        ret = await sim.wait(1, cond=fut)
    assert ret is None
    assert sim.time == time + 1

    # Test await cond
    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim).schedule(0))
    DSProcess(signal_future_after(2, cond)).schedule(0)
    ret = await cond
    assert ret == 'Signal!'
    assert sim.time == time + 2
    
    # Test await cond.wait
    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim).schedule(0))
    DSProcess(signal_future_after(2, cond)).schedule(0)
    ret = await cond.wait()
    assert ret == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim).schedule(0))
    DSProcess(signal_future_after(2, cond)).schedule(0)
    ret = await cond.wait(1)
    assert ret is None
    assert sim.time == time + 1

    # Test await sim.wait
    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim).schedule(0))
    DSProcess(signal_future_after(1, cond)).schedule(0)
    with sim.observe_pre(cond):
        ret = await sim.wait(cond=cond)
    assert ret == 'Signal!'
    assert sim.time == time + 1

    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim).schedule(0))
    DSProcess(signal_future_after(2, cond)).schedule(0)
    with sim.observe_pre(cond):
        ret = await sim.wait(1, cond=cond)
    assert ret is None
    assert sim.time == time + 1

    
async def demo_filtering4():
    ''' Testing f(process) | f(process) '''
    # Test await cond
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    ret = await (cond0 | cond1)
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    # Test await cond.wait
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 | cond1)
    ret = await cond.wait()
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 | cond1)    
    ret = await cond.wait(1)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

    # Test await sim.wait
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 | cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(cond=cond)
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 | cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(1, cond=cond)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

async def demo_filtering5():
    ''' Testing f(process) & f(process) '''
    # Test await cond
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    ret = await (cond0 & cond1)
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    # Test await cond.wait
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 & cond1)
    ret = await cond.wait()
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 & cond1)    
    ret = await cond.wait(1)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1

    # Test await sim.wait
    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 & cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(cond=cond)
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim).schedule(0))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim).schedule(0))
    cond = (cond0 & cond1)
    with sim.observe_pre(cond):
        ret = await sim.wait(1, cond=cond)
    assert ret == {}
    assert cond.value is None
    assert sim.time == time + 1


async def demo_filtering():
    await demo_filtering0()
    await demo_filtering1()
    await demo_filtering2()
    await demo_filtering3()
    await demo_filtering4()
    await demo_filtering5()

if __name__ == '__main__':
    sim = DSSimulation()
    proc = sim.schedule(0, demo_filtering())
    retval = sim.run()
    assert retval == (135, 253)
