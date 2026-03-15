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
DSDelay component example (pubsub layer).
'''
from dssim import DSSimulation


if __name__ == '__main__':
    sim = DSSimulation()
    delay = sim.delay(2, name='delay')
    received = []

    sink = sim.callback(lambda e: received.append((sim.time, e)), name='sink')
    delay.tx.add_subscriber(sink)

    sim.schedule_event(1, 'A', delay.rx)
    sim.schedule_event(2, 'B', delay.rx)
    sim.run(10)

    print('Received:', received)
    assert received == [(3, 'A'), (4, 'B')]
