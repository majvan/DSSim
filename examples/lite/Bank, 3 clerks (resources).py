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
LiteLayer2 counterpart of examples/pubsub/Bank, 3 clerks (resources).py.
'''
import random

from dssim import DSSimulation, DSLiteAgent, LiteLayer2


class CustomerGenerator(DSLiteAgent):
    def process(self):
        while True:
            Customer(sim=self.sim)
            yield from self.gwait(random.uniform(5, 15))


class Customer(DSLiteAgent):
    def process(self):
        yield from self.gget(clerks)
        print(f"{self.sim.time} Customer in process with clerk")
        yield from self.gwait(30)
        yield from self.gput(clerks)


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    CustomerGenerator(sim=sim)
    clerks = sim.resource(amount=3, name="clerks")

    time, events = sim.run(50000)
    assert 49950 < time <= 50000, f"Time {time} is out of expected range."
    assert 19000 < events < 40000, f"Number of events {events} is out of expected range."
