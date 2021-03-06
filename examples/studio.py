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
from dssim.simulation import sim, DSComponent, DSAbortException
from random import randint

class Studio(DSComponent):
    def __init__(self):
        # Prepare moderator
        moderator = self.moderator_process()
        # Prepare speakers to talk
        self.speakers = [self.speaker_process() for i in range(20)]
        # Start the role of moderator
        self.moderator = sim.schedule(0, moderator)

    def speaker_process(self):
        try:
            yield from sim.wait(randint(20, 40))
            print('Speaker finished')
            sim.signal(self.moderator)
        except DSAbortException as e:
            print(e.info['msg'])

    def moderator_process(self):
        for s in self.speakers:
            sim.schedule(0, s)  # Invite next speaker
            result = yield from sim.wait(30, cond=lambda e: True)
            if result is None:
                # We finished with timeout
                sim.abort(s, msg='No time left')

s = Studio()
sim.run(1000)
