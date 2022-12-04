# Copyright 2021 NXP Semiconductors
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
from dssim.simulation import DSSimulation
from dssim.processcomponent import DSProcessComponent
from dssim.pubsub import DSProducer
import random


class CustomerGenerator(DSProcessComponent):
    def process(self):
        while True:
            Customer()
            yield from self.wait(random.uniform(5, 15))


class Customer(DSProcessComponent):
    def process(self):
        waitingline.append(self)
        signaler.signal('there is some work to do')  # the observers and consumers are being notified


class Clerk(DSProcessComponent):
    def process(self, i):
        while True:
            if len(waitingline) == 0:
                msg = yield from signaler.wait()  # create a consumer and wait for any signal from the producer
            customer = waitingline.pop()
            print(f"{self.sim.time} Customer in process with clerk {i}")
            yield from self.wait(30)


sim = DSSimulation() 
CustomerGenerator()
for i in range(3):
    Clerk(i)
waitingline = []  # we could use Queue as well, but it does not make a sense because we do not use it for signaling
signaler = DSProducer(name="worktodo")

sim.run(50000)
# waitingline.print_histograms()
# worktodo.print_histograms()
