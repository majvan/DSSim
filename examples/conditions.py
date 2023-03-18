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


def return_hello_after_10():
    yield from sim.gwait(10)
    return 'hello'

def signal_after_time(time, cond):
    yield from sim.gwait(time)
    cond.finish('Signal!')

async def demo_filtering():
    time = sim.time
    cond = f(DSProcess(return_hello_after_10(), name='original_process_waiting_for', sim=sim))
    DSProcess(signal_after_time(1, cond), name='async_setter_process').schedule(0)
    ret = await cond
    assert ret == 'Signal!'
    assert sim.time == time + 1

    ret = await sim.wait(6, cond)


if __name__ == '__main__':
    sim = DSSimulation()
    proc = sim.schedule(0, demo_filtering())
    retval = sim.run()
    assert retval == (10, 9)
