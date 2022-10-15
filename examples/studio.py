# Copyright 2020 NXP Semiconductors
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
from dssim.simulation import DSComponent, DSAbortException, DSSimulation
from random import randint

NUM_OF_SPEAKERS = 20

class Studio(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prepare moderator
        moderator = self.moderator_process()
        # Prepare speakers to talk
        self.speakers = [self.speaker_process() for i in range(NUM_OF_SPEAKERS)]
        # Start the role of moderator
        self.moderator = self.sim.schedule(0, moderator)
        self.stat = {'abort': 0, 'finish': 0}

    def speaker_process(self):
        try:
            yield from sim.wait(randint(20, 40))
            print('Speaker finished')
            self.stat['finish'] += 1
            sim.signal(self.moderator)
        except DSAbortException as e:
            print(e.info['msg'])
            self.stat['abort'] += 1

    def moderator_process(self):
        for s in self.speakers:
            sim.schedule(0, s)  # Invite next speaker
            result = yield from sim.wait(30, cond=lambda e: True)
            if result is None:
                # We finished with timeout
                sim.abort(s, msg='No time left')

if __name__ == '__main__':
    sim = DSSimulation()
    s = Studio(sim=sim)
    sim.run(1000)

    assert s.stat['finish'] > 0  # high probability to pass
    assert s.stat['abort'] > 0  # high probability to pass
    assert s.stat['finish'] + s.stat['abort'] == NUM_OF_SPEAKERS
