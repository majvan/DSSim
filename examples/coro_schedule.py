# Copyright 2020- majvan (majvan@gmail.com)
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
Plain generator / coroutine scheduling using SimWaitMixin.gwait / wait.

process_schedule.py wraps generators in DSProcess (via DSComponent) and uses
SimProcessMixin.gwait which is condition-aware.

This file shows the same timing logic using plain generator functions and async
coroutines with no DSProcess or DSComponent.  sim.gwait() / sim.wait() come
from SimWaitMixin — they accept any arriving event or return None on timeout.

Key difference from process_schedule.py:
  process_schedule.py  ->  DSComponent + SimProcessMixin.gwait (condition-aware)
  coro_schedule.py     ->  standalone generators + SimWaitMixin.gwait (timeout only)
'''
from dssim import DSSimulation, TinyLayer2


# ---------------------------------------------------------------------------
# Generator variants — use yield from sim.gwait(timeout)
# ---------------------------------------------------------------------------

def do_somethingA(sim):
    assert sim.time == 10
    print(sim.time, 'taskA', '0 Sleeping for 5 sec')
    yield from sim.gwait(5)
    assert sim.time == 15
    print(sim.time, 'taskA', '1 Sleeping for 2 sec')
    yield from sim.gwait(2)
    assert sim.time == 17
    print(sim.time, 'taskA', '2 Finish')


def do_somethingB(sim):
    assert sim.time == 14
    print(sim.time, 'taskB', '0 Sleeping for 1 sec')
    yield from sim.gwait(1)
    assert sim.time == 15
    print(sim.time, 'taskB', '1 Sleeping for 3 sec')
    yield from sim.gwait(3)
    assert sim.time == 18
    print(sim.time, 'taskB', '2 Finish')


def do_somethingC(sim, taskA, taskB):
    assert sim.time == 8
    print(sim.time, 'taskC', '0 Scheduling taskA in 2 sec')
    sim.schedule(2, taskA)
    print(sim.time, 'taskC', '0 Sleeping for 4 sec')
    yield from sim.gwait(4)
    assert sim.time == 12
    print(sim.time, 'taskC', '1 Scheduling taskB in 2 sec')
    sim.schedule(2, taskB)
    print(sim.time, 'taskC', '2 Finish')


# ---------------------------------------------------------------------------
# Coroutine variants — use await sim.wait(timeout)
# ---------------------------------------------------------------------------

async def do_somethingA_async(sim):
    assert sim.time == 10
    print(sim.time, 'taskA_async', '0 Sleeping for 5 sec')
    await sim.wait(5)
    assert sim.time == 15
    print(sim.time, 'taskA_async', '1 Sleeping for 2 sec')
    await sim.wait(2)
    assert sim.time == 17
    print(sim.time, 'taskA_async', '2 Finish')


async def do_somethingB_async(sim):
    assert sim.time == 14
    print(sim.time, 'taskB_async', '0 Sleeping for 1 sec')
    await sim.wait(1)
    assert sim.time == 15
    print(sim.time, 'taskB_async', '1 Sleeping for 3 sec')
    await sim.wait(3)
    assert sim.time == 18
    print(sim.time, 'taskB_async', '2 Finish')


async def do_somethingC_async(sim, taskA, taskB):
    assert sim.time == 8
    print(sim.time, 'taskC_async', '0 Scheduling taskA in 2 sec')
    sim.schedule(2, taskA)
    print(sim.time, 'taskC_async', '0 Sleeping for 4 sec')
    await sim.wait(4)
    assert sim.time == 12
    print(sim.time, 'taskC_async', '1 Scheduling taskB in 2 sec')
    sim.schedule(2, taskB)
    print(sim.time, 'taskC_async', '2 Finish')


if __name__ == '__main__':
    sim = DSSimulation(layer2=TinyLayer2)

    # --- generator set ---
    print('=== generator variant ===')
    taskA = do_somethingA(sim)
    taskB = do_somethingB(sim)
    taskC = do_somethingC(sim, taskA, taskB)
    sim.schedule(8, taskC)
    sim.run(20)
    assert sim.time == 20

    sim.restart()

    # --- coroutine set ---
    print('=== coroutine variant ===')
    taskA_a = do_somethingA_async(sim)
    taskB_a = do_somethingB_async(sim)
    taskC_a = do_somethingC_async(sim, taskA_a, taskB_a)
    sim.schedule(8, taskC_a)
    sim.run(20)
    assert sim.time == 20

    print('All assertions passed.')
