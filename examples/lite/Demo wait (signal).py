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
"""
LiteLayer2 counterpart of examples/pubsub/Demo wait (signal).py.

Without pubsub consume/check-and-wait primitives, we model the wakeup policy
explicitly: when a king dies, the youngest waiting prince is signaled.
"""
import random

from dssim import DSSimulation, DSLiteAgent, LiteLayer2


def _signal_next_heir() -> None:
    '''Wake the youngest waiting prince (LIFO over wait registration).'''
    while waiting_princes:
        prince = waiting_princes.pop()
        if prince._waiting_for_throne and sim.time < prince.live_till:
            prince._waiting_for_throne = False
            prince.signal('king died')
            return


class PrinceGenerator(DSLiteAgent):
    def process(self):
        while True:
            # every 10-20 years there's a new heir of the throne
            yield from self.gwait(int(random.expovariate(1 / 20)))
            Prince(sim=self.sim)


class Prince(DSLiteAgent):
    def process(self):
        global king, kings, lastkingdied
        self.live_till = self.sim.time + random.randint(60, 90)
        self._waiting_for_throne = False
        print(self.sim.time, self, "going to live till", self.live_till)
        if king is None:
            kings.append(("no king", lastkingdied, self.sim.time, self.sim.time - lastkingdied))
        else:
            self._waiting_for_throne = True
            waiting_princes.append(self)
            event = yield from self.gwait(self.live_till - self.sim.time)
            if not event:
                self._waiting_for_throne = False
                print(self.sim.time, self, "dies before getting to the throne")
                return
        king = self
        print(self.sim.time, self, "Vive le roi!")
        kings.append((self.name, self.sim.time, self.live_till, self.live_till - self.sim.time))
        yield from self.gwait(self.live_till - self.sim.time)
        king, lastkingdied = None, self.sim.time
        print(self.sim.time, self, "Le roi est mort.")
        _signal_next_heir()


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    lastkingdied = sim.time
    kings = []
    king = None
    waiting_princes = []
    PrinceGenerator(sim=sim)

    sim.run(5000)
    print("king                     from       to duration")
    for king_record in kings:
        print("{:20}{:9d}{:9d}{:9d}".format(*king_record))

    assert 209 <= Prince._dsliteagent_instances <= 310, (
        f"Num of kings {Prince._dsliteagent_instances} is out of expected range."
    )
    no_king_periods = sum(int(k[3] == 0) for k in kings)
    assert no_king_periods <= 8, (
        f"Num of period without kings {no_king_periods} is out of expected range."
    )
