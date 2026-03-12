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
LiteLayer2 counterpart of examples/pubsub/Bank, 1 clerk.py.
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
        queued = self.enter_nowait(waitingline)
        if queued is None:
            stat['balked'] += 1
            return
        event = yield from self.gwait()
        print(f"{self.sim.time} Customer ends with signal {event}")
        stat['completed'] += 1


class Clerk(DSLiteAgent):
    def process(self):
        self.processed = 0
        while True:
            customer = yield from self.gpop(waitingline)
            print(f"{self.sim.time} Processing customer")
            yield from self.gwait(30)
            customer.signal("processed")
            self.processed += 1


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    CustomerGenerator(sim=sim)
    clerk = Clerk(sim=sim)
    waitingline = sim.queue(name="waitingline")
    stat = {'completed': 0, 'balked': 0}

    time, events = sim.run(50)
    assert 35 <= time <= 50, f"Time {time} is out of expected range."
    assert 14 <= events <= 21, f"Number of events {events} is out of expected range."
    assert clerk.processed >= 1, "Expected at least one processed customer."
    assert stat['completed'] == clerk.processed, (
        f"Completed customers ({stat['completed']}) should match processed count ({clerk.processed})."
    )
