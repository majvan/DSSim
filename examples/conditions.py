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
from dssim.simulation import DSSimulation


def return_apologize_after_10():
    yield from sim.gwait(10)
    return {'apologize': 'sorry'}

def waiting_for_table_service():
    t0, t1, t2 = sim.schedule_event(4, {'tool': 'knife'}), sim.schedule_event(6, {'tool': 'fork'}), sim.schedule_event(4, {'tool': 'spoon'})
    cond = f({'food': 'ham'}) & f({'food': 'eggs'}) & f({'drink': 'tea'}) & f({'tool': 'fork'}) & f({'tool': 'knife'}) | \
        f({'food': 'yogurt'}) & f({'food': 'muesli'}) & (f({'drink': 'milk'}) | f({'drink': 'juice'})) & f({'tool': 'spoon'})
    # print(cond)  # here you can printout the condition
    ret = yield from sim.gwait(30, cond=cond)
    assert tuple(ret.values()) == ({'food': 'yogurt'}, {'food': 'muesli'}, {'drink': 'milk'}, {'tool': 'spoon'})
    if ret is not None:
        ret = {'service': 'good'}
    return ret
    
def demo_filtering():
    time = sim.time
    t0 = sim.schedule_event(3, {'greeting': 'hello'})
    t1 = sim.schedule_event(4, {'greeting': 'I dont like you'})
    t2 = sim.schedule_event(5, {'greeting': 'world'})
    # The following OR is a bit artificial (or-ing 2 same structures), but it will be constructed. See
    # the next case for explanation why we constructed it.
    ret = yield from sim.gwait(6, cond=-f(t1) | (f(t0) & f(t2)) | (f(t2) & f(t0)))
    assert sim.time == time + 5

    time = sim.time
    t0 = sim.schedule_event(3, {'greeting': 'hello'})
    t1 = sim.schedule_event(4, {'greeting': 'I dont like you'})
    t2 = sim.schedule_event(5, {'greeting': 'world'})
    ret = yield from sim.gwait(6, cond=-f(t1) & (f(t0) & f(t2)) | (f(t2) & f(t0)))
    assert sim.time == time + 5

    # Test compounded expressions in the resetter
    time = sim.time
    t0 = sim.schedule_event(3, {'greeting': 'hello'})
    t1 = sim.schedule_event(4, {'greeting': 'I dont like you'})
    t2 = sim.schedule_event(5, {'greeting': 'world'})
    t3 = sim.schedule_event(6, {'greeting': 'Neither I like you'})
    t4 = sim.schedule_event(7, {'greeting': '!'})
    t5 = sim.schedule_event(8, {'greeting': 'hello'})
    t6 = sim.schedule_event(9, {'greeting': 'world'})
    ret = yield from sim.gwait(10, cond=-(f(t1) & f(t3)) & f(t0) & f(t2) & f(t4))
    assert sim.time == time + 9

    time = sim.time
    t0 = sim.schedule_event(3, {'greeting': 'hello'})
    t1 = sim.schedule_event(4, {'greeting': 'world'})
    t2 = sim.schedule_event(5, {'greeting': 'I dont like you'})
    t3 = sim.schedule_event(6, {'greeting': '!'})
    t4 = sim.schedule_event(7, {'greeting': 'hello'})
    t5 = sim.schedule_event(8, {'greeting': 'world'})
    t6 = sim.schedule_event(9, {'greeting': 'Neither I like you'})
    ret = yield from sim.gwait(10, cond=-(f(t6) | f(t2)) & f(t0) & f(t1) & f(t3))
    assert sim.time == time + 8
    sim.delete(cond=lambda e:True)

    time = sim.time
    t1, t2 = sim.schedule_event(1, {'value': 'ham'}), sim.schedule_event(2, {'value': 'eggs'})
    ret = yield from sim.gwait(cond=f(t1) & f(t2))
    assert tuple(ret.values()) == ({'value': 'ham'}, {'value': 'eggs'})
    assert sim.time == time + 2
    print(ret)
    
    time = sim.time
    t1, t2 = sim.schedule_event(1, {'value': 'ham'}), sim.schedule_event(2, {'value': 'eggs'})
    ret = yield from sim.gwait(cond=f(t1) | f(t2))
    assert tuple(ret.values()) == ({'value': 'ham'},)
    assert sim.time == time + 1
    print(ret)
    sim.delete(cond=lambda e:True)

    time = sim.time
    t1, t2, t3 = [sim.schedule_event(i, i + 1) for i in range(3)]
    ret = yield from sim.gwait(cond=f(t1) & f(t2) | f(t3))
    assert tuple(ret.values()) == (1, 2)  # after t1 and t2 it should finish, so the last is t2
    assert sim.time == time + 1
    print(ret)  
    sim.delete(cond=lambda e:True)

    time = sim.time
    t1, t2, t3 = sim.schedule_event(3, {'value': 'ham'}), sim.schedule_event(1, {'value': 'ham'}), sim.schedule_event(2, {'value': 'eggs'})
    ret = yield from sim.gwait(cond=f(t1) & f(t2) | f(t3))
    assert tuple(ret.values()) == ({'value': 'ham'}, {'value': 'ham'})  # the first event {'value': 'ham'} satisfies both f(t1) and f(t2) filters, hence it finishes after 1 second
    assert sim.time == time + 1
    print(ret)
    sim.delete(cond=lambda e:True)

    time = sim.time
    t1, t2 = sim.schedule_event(1, {'food': 'ham'}), sim.schedule_event(2, {'food': 'eggs'}),
    t3, = sim.schedule_event(3, {'drink': 'tea'}),
    t4, t5 = sim.schedule_event(4, {'tool': 'knife'}), sim.schedule_event(6, {'tool': 'fork'}), 
    ret = yield from sim.gwait(cond=f(lambda e:'food' in e) & f(t4) & f(t5) | f(lambda e:'drink' in e))
    assert tuple(ret.values()) == ({'drink': 'tea'},)  # waiting for either food with tools or a drink - first we are satisfied with the drink
    assert sim.time == time + 3
    print(ret)
    sim.delete(cond=lambda e:True)

    time = sim.time
    t0 = sim.schedule_event(10, {'apologize': 'sorry'})
    t1, t2 = sim.schedule_event(3, {'food': 'ham'}), sim.schedule_event(1, {'food': 'eggs'}), 
    t3, t4 = sim.schedule_event(5, {'food': 'yogurt'}), sim.schedule_event(2, {'food': 'muesli'}),
    t5, t6, t7 = sim.schedule_event(7, {'drink': 'tea'}), sim.schedule_event(6, {'drink': 'juice'}), sim.schedule_event(3, {'drink': 'milk'}),
    ret = yield from sim.gwait(cond=f(waiting_for_table_service(), sim=sim) | f(t0))
    # We were served with yogurt + muesli + milk + spoon in table service; but the waiting_for_table_service returns only one event
    assert tuple(ret.values()) == ({'service': 'good'},)
    assert sim.time == time + 5
    print(ret)
    sim.delete(cond=lambda e:True)

    # Test case: A generator "return_greetings_after_10" is going to send event after we return from wait. We should not be affected.
    time = sim.time
    t0 = sim.schedule_event(3, {'greeting': 'hello'})
    ret = yield from sim.gwait(cond=f(t0) | f(return_apologize_after_10(), sim=sim))
    assert tuple(ret.values()) == ({'greeting': 'hello'},)
    assert sim.time == time + 3
    ret = yield from sim.gwait(30, cond=lambda e:True)
    assert ret == None
    assert sim.time == time + 33

    time = sim.time
    ret = yield from sim.gwait(cond=f(sim.gwait(2), signal_timeout=True, sim=sim) & f(sim.gwait(6), signal_timeout=True, sim=sim) | f(sim.gwait(4), signal_timeout=True, sim=sim) & f(sim.gwait(5), signal_timeout=True, sim=sim))
    assert sim.time == time + 5  # wait for (2 and 6) or (1 and 5) => signal at 1 then 5 makes this true
    assert tuple(ret.values()) == (None, None)


if __name__ == '__main__':
    sim = DSSimulation()
    proc = sim.schedule(0, demo_filtering())
    sim.run()
