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
Limiter component example (lite layer).
'''
from dssim import DSSimulation, LiteLayer2


class Sink:
    supports_direct_send = True

    def __init__(self, sim, out):
        self.sim = sim
        self.out = out

    def send(self, event):
        self.out.append((self.sim.time, event))
        return True


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    limiter = sim.limiter(throughput=2, name='limiter')  # one event every 0.5 time units
    received = []
    limiter.tx.add_subscriber(Sink(sim, received))

    for i in range(5):
        sim.signal(i, limiter.rx)
    sim.run(5)

    print('Received:', received)
    assert [(round(t, 3), e) for t, e in received] == [(0.0, 0), (0.5, 1), (1.0, 2), (1.5, 3), (2.0, 4)]
