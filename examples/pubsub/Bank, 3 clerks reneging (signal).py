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


class CustomerGenerator(sim.Component):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(5)  # If needed: random.randint(5, 15)


class Customer(sim.Component):
    def process(self):
        entered = self.enter_nowait(waiting_line)
        if entered is None:
            stat['balked'] += 1
            # env.print_trace("", "", "balked")
            # print(env.now(), stat['balked'], self.name)            
            return
        clerk = yield from self.gwait(50)  # wait until we get a 'start' signal from a clerk
        if clerk is None:  # did we get the signal?
            self.leave(waiting_line)
            stat['reneged'] += 1
            # env.print_trace("", "", "reneged")


class Clerk(sim.Component):
    def process(self):
        while True:
            customer = yield from waiting_line.gget()  # get from the queue if available
            customer.signal(self)  # signal the customer that we started processing
            yield from self.gwait(30)


env = sim.Environment()
CustomerGenerator()
stat = {'balked': 0, 'reneged': 0}
clerks = [Clerk() for _ in range(3)]
waiting_line = sim.Queue(5, name="waiting_line")
waiting_line_probe = waiting_line.add_stats_probe(name='users')
time, events = env.run(300000)
# waiting_line.length.print_histogram(30, 0, 1)
# waiting_line.length_of_stay.print_histogram(30, 0, 10)
print("number reneged", stat['reneged'])
print("number balked", stat['balked'])
waiting_line_stats = waiting_line_probe.get_statistics()
print(
    f'Summary: {waiting_line_probe.name} '
    f'avg_len={waiting_line_stats["time_avg_len"]:.3f}, '
    f'max_len={waiting_line_stats["max_len"]}, '
    f'nonempty_ratio={waiting_line_stats["time_nonempty_ratio"]:.3f}, '
    f'puts={waiting_line_stats["put_count"]}, '
    f'gets={waiting_line_stats["get_count"]}'
)
assert stat['reneged'] == 6665, f"Unexpected number of reneged."
assert stat['balked'] == 23330, f"Unexpected number of balked."
assert time == 299995, f"Time {time} is out of expected range."
# Queue probe callbacks add observer work, so total event count is higher than the uninstrumented variant.
assert events == 319995, f"Number of events {events} is out of expected range."
