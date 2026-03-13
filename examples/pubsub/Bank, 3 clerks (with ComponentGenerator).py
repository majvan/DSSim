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
from dssim.pubsub.parity import salabim as sim
import random


class Customer(sim.Component):
    def process(self):        
        self.enter_nowait(waitingline)


class Clerk(sim.Component):
    def process(self):
        while True:
            customer = yield from self.gpop(waitingline)
            print(f"{self.sim.time} Processing customer")
            yield from self.gwait(30)
            customer.signal("processed")


env = sim.Environment()
sim.ComponentGenerator(Customer, wait_method= lambda e: random.uniform(5, 15))
clerks = [Clerk() for _ in range(3)]
waitingline = sim.Queue(name="waitingline")
waitingline_probe = waitingline.add_stats_probe(name='users')

time, events = env.run(50000)
waitingline_stats = waitingline_probe.get_statistics()
print(
    f'Summary: {waitingline_probe.name} '
    f'avg_len={waitingline_stats["time_avg_len"]:.3f}, '
    f'max_len={waitingline_stats["max_len"]}, '
    f'nonempty_ratio={waitingline_stats["time_nonempty_ratio"]:.3f}, '
    f'puts={waitingline_stats["put_count"]}, '
    f'gets={waitingline_stats["get_count"]}'
)
# waitingline.print_histograms()
assert 49950 < time <= 50000, f"Time {time} is out of expected range."
assert 20000 < events < 40000, f"Number of events {events} is out of expected range."
