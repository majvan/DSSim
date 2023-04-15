# Copyright 2022- majvan (majvan@gmail.com)
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
"""
An example showing a parity with salabim app code. Inspired from salabim.
Here, princes, are generated.
In the meantime, kings die.
The youngest prince, will become king.

If a new prince arrives, he checks, whether there's a king.
If so, he will wait for a kingdied trigger.
If not, he will become king.

Note that in this demo, the priority (-now) in wait is used to make
the youngest prince to become king.

This is demo of the trigger/waitfor mechanism,
just to allow one waiter to be honored.
"""
from dssim import DSSimulation, DSAbsTime as _abs, DSProducer, DSProcessComponent
import random


class PrinceGenerator(DSProcessComponent):
    def process(self):
        while True:
            yield from self.sim.gwait(int(random.expovariate(1/20)))  # every 10-20 years othere's a new heir of the throne
            Prince()


class Prince(DSProcessComponent):
    def process(self):
        global king, kings, lastkingdied
        self.live_till = self.sim.time + random.randint(60, 90)
        print(self.sim.time, self, "going to live till", self.live_till)
        if king is None:  # there is no king, so this prince will become king, immediately
            kings.append(("no king", lastkingdied, self.sim.time, self.sim.time - lastkingdied))
        with self.sim.consume(king_died):  # we consume event and noone else gets notified
            event = yield from self.sim.check_and_gwait(_abs(self.live_till), cond=lambda e: king is None)  # any message will interrupt, because only king died messages are sent here
            if not event:  # timeout returns None event
                print(self.sim.time, self, "dies before getting to the throne")
                return
        king = self
        print(self.sim.time, self, "Vive le roi!")
        kings.append((self.name, self.sim.time, self.live_till, self.live_till - self.sim.time))
        yield from self.sim.gwait(_abs(self.live_till))
        king, lastkingdied = None, self.sim.time
        print(self.sim.time, self, "Le roi est mort.")
        king_died.signal('king died')


sim = DSSimulation()
lastkingdied = sim.time
kings = []
king_died = DSProducer(name='king died')  # we do not need State for this, all we need is simple notification routing
king = None
PrinceGenerator()

sim.run(5000)
print("king                     from       to duration")
for king in kings:
    print("{:20}{:9d}{:9d}{:9d}".format(*king))
