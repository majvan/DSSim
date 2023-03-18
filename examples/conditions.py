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
from dssim.cond import DSFilter as f
from dssim.simulation import DSSimulation, DSProcess


def return_greeting_after(time, greeting):
    yield from sim.gwait(time)
    return greeting

def signal_cond_after(time, cond):
    yield from sim.gwait(time)
    cond.finish('Signal!')

async def demo_filtering():
    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim))
    DSProcess(signal_cond_after(2, cond)).schedule(0)
    ret = await cond
    assert ret == 'Signal!'
    assert sim.time == time + 2
    
    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim))
    DSProcess(signal_cond_after(2, cond)).schedule(0)
    ret = await cond.wait()
    assert ret == 'Signal!'
    assert sim.time == time + 2

    time = sim.time
    cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim))
    DSProcess(signal_cond_after(2, cond)).schedule(0)
    ret = await cond.wait(1)
    assert ret is None
    assert sim.time == time + 1

    # time = sim.time
    # cond = f(DSProcess(return_greeting_after(10, 'hello'), sim=sim))
    # DSProcess(signal_cond_after(1, cond)).schedule(0)
    # ret = await sim.wait(cond=cond)
    # assert ret == 'Signal!'
    # assert sim.time == time + 1

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 | cond1)
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 | cond1).wait()
    assert ret == {cond1: 'hello'}
    assert sim.time == time + 5

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 | cond1).wait(1)
    assert ret is None
    assert sim.time == time + 1

    # time = sim.time
    # cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    # cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    # ret = await sim.wait(cond=cond0 | cond1)
    # assert ret == {cond1: 'hello'}
    # assert sim.time == time + 5

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 & cond1)
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 & cond1).wait()
    assert ret == {cond0: 'hi', cond1: 'hello'}
    assert sim.time == time + 10

    time = sim.time
    cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    ret = await (cond0 & cond1).wait(1)
    assert ret is None
    assert sim.time == time + 1

    # time = sim.time
    # cond0 = f(DSProcess(return_greeting_after(10, 'hi'), sim=sim))
    # cond1 = f(DSProcess(return_greeting_after(5, 'hello'), sim=sim))
    # ret = await sim.wait(cond=cond0 & cond1)
    # assert ret == {cond0: 'hi', cond1: 'hello'}
    # assert sim.time == time + 5

    ret = await sim.wait(6, cond)


if __name__ == '__main__':
    sim = DSSimulation()
    proc = sim.schedule(0, demo_filtering())
    retval = sim.run()
    assert retval == (46, 66)
