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
A resource is an object representing a pool of abstract resources with amount filled in.
Compared to queue, resource works with non-integer amounts but it does not contain object
in the pool, just an abstract pool level information (e.g. amount of water in a tank).
'''
from dssim.simulation import DSComponent, DSSchedulable
from dssim.pubsub import DSProducer


class State(DSComponent):
    ''' The State components holds a dictionary of state variables and their values.
    '''
    def __init__(self, state={}, *args, **kwargs):
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.tx_changed = DSProducer(name=self.name+'.tx', sim=self.sim)
        self.state = state

    def __setitem__(self, key, value):
        if (key not in self.state) or self.state[key] != value:
            self.state[key] = value
            self.tx_changed.schedule_event(0, 'resource changed')
            return True
        return False

    def __getitem__(self, key):
        return self.state[key]

    def get(self, key, default=None):
        return self.state.get(key, default)

    def check_and_wait(self, timeout=float('inf'), cond=lambda e:True):
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_wait(timeout, cond=cond)
        return retval

    def wait(self, timeout=float('inf'), cond=lambda e:True):
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.wait(timeout, cond=cond)
        return retval
