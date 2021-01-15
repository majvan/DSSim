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
'''
The example is showing a code parity with example from salabim project
'''
from dssim import DSSimulation, DSAgent
import random


class CustomerGenerator(DSAgent):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(random.uniform(5, 15))


class Customer(DSAgent):
    def process(self):
        queued = self.enter_nowait(waitingline)
        if queued is None:
            stat['balked'] += 1
            return
        event = yield from self.gwait()  # wait any event to be activated
        print(f"{self.sim.time} Customer ends with signal {event}")
        stat['completed'] += 1


class Clerk(DSAgent):
    def process(self):
        self.processed = 0
        while True:
            customer = yield from self.gpop(waitingline)
            print(f"{self.sim.time} Processing customer")
            yield from self.gwait(30)
            customer.signal("processed")
            self.processed += 1


sim = DSSimulation()

CustomerGenerator()
clerk = Clerk()
waitingline = sim.queue(name="waitingline")
waitingline_probe = waitingline.add_stats_probe(name='users')
stat = {'completed': 0, 'balked': 0}

time, events = sim.run(50)
print()
waitingline_stats = waitingline_probe.get_statistics()
print(
    f'Summary: {waitingline_probe.name} '
    f'avg_len={waitingline_stats["time_avg_len"]:.3f}, '
    f'max_len={waitingline_stats["max_len"]}, '
    f'nonempty_ratio={waitingline_stats["time_nonempty_ratio"]:.3f}, '
    f'puts={waitingline_stats["put_count"]}, '
    f'gets={waitingline_stats["get_count"]}'
)
# waitingline.print_statistics()
assert 35 <= time <= 50, f"Time {time} is out of expected range."
assert clerk.processed >= 1, "Expected at least one processed customer."
assert stat['completed'] == clerk.processed, (
    f"Completed customers ({stat['completed']}) should match processed count ({clerk.processed})."
)
