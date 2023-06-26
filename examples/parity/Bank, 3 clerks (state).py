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
from dssim import DSSimulation, DSProcessComponent, State
import random


class CustomerGenerator(DSProcessComponent):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(random.uniform(5, 15))


class Customer(DSProcessComponent):
    def process(self):
        waitingline.append(self)
        worktodo['waiting on line'] = True


class Clerk(DSProcessComponent):
    def process(self):
        while True:
            retval = yield from worktodo.check_and_gwait(cond=lambda e:worktodo['waiting on line'])  # wait until worktodo['waiting on line'] is True
            customer = waitingline.pop()
            worktodo['waiting on line'] = (len(waitingline) > 0)  # this operation can change the state => it sends a signal
            print(f"{self.sim.time} Customer in process with clerk")
            yield from self.gwait(30)


sim = DSSimulation() 
CustomerGenerator()
for i in range(3):
    Clerk()
waitingline = []  # we could use Queue as well, but it does not make a sense because we do not use it for signaling
worktodo = State({'waiting on line': False}, name="worktodo")

time, events = sim.run(50000)
# waitingline.print_histograms()
# worktodo.print_histograms()
assert 49950 < time <= 50000, f"Time {time} is out of expected range."
assert 20000 < events < 50000 / 30 * 3 * 6 + 30, f"Number of events {events} is out of expected range."
