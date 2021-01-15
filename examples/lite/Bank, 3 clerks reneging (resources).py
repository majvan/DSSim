# Copyright 2026- majvan (majvan@gmail.com)
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
LiteLayer2 counterpart of examples/pubsub/Bank, 3 clerks reneging (resources).py.
'''
from dssim import DSSimulation, DSLiteAgent, LiteLayer2


class CustomerGenerator(DSLiteAgent):
    def process(self):
        while True:
            Customer(sim=self.sim)
            yield from self.gwait(5)


class Customer(DSLiteAgent):
    waiting = 0

    def process(self):
        if Customer.waiting >= 5:
            stat['balked'] += 1
            return
        Customer.waiting += 1
        clerk_amount = yield from self.gget(clerks, timeout=50)
        Customer.waiting -= 1
        if clerk_amount == 0:
            stat['reneged'] += 1
        else:
            yield from self.gwait(30)
            self.put_nowait(clerks)


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    CustomerGenerator(sim=sim)
    stat = {'balked': 0, 'reneged': 0}
    clerks = sim.resource(amount=3, name="clerks")
    time, events = sim.run(300000)
    print("number reneged", stat['reneged'])
    print("number balked", stat['balked'])

    assert time == 299995, f"Time {time} is out of expected range."
    assert stat['reneged'] > 0, "Expected at least one reneged customer."
    assert stat['balked'] > 0, "Expected at least one balked customer."
