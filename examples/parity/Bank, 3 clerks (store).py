# Copyright 2022- majvan (majvan@gmail.com)
# Copyright 2022 NXP Semiconductors
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
The example is showing a code parity with example from salabim project
'''
from dssim.parity import salabim as sim
import random


class CustomerGenerator(sim.Component):
    def process(self):
        while True:
            Customer().enter_nowait(waiting_room)
            yield from self.gwait(random.uniform(5, 15))


class Clerk(sim.Component):
    def process(self):
        while True:
            customer = yield from self.gpop(waiting_room)
            print(f"{self.sim.time} Customer in process with clerk")
            yield from self.gwait(30)


class Customer(sim.Component):
    ...


env = sim.Environment()
CustomerGenerator()
for _ in range(3):
    Clerk()
waiting_room = sim.Store(name="waiting_room")
time, events = env.run(50000)
# waitingline.print_histograms()
# worktodo.print_histograms()
assert 49950 < time <= 50000, f"Time {time} is out of expected range."
assert 20000 < events < 40000, f"Number of events {events} is out of expected range."
