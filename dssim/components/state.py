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
from typing import Dict, Any, TYPE_CHECKING
from dssim.base import TimeType, EventType, CondType, DSStatefulComponent


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class State(DSStatefulComponent):
    ''' The State components holds a dictionary of state variables and their values.
    '''
    def __init__(self, state: Dict = {}, *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.state = state

    def __setitem__(self, key: Any, value: Any) -> bool:
        if (key not in self.state) or self.state[key] != value:
            self.state[key] = value
            self.tx_changed.schedule_event(0, 'resource changed')
            return True
        return False

    def __getitem__(self, key: Any) -> Any:
        return self.state[key]

    def get(self, key: Any, default: Any = None) -> Any:
        return self.state.get(key, default)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimStateMixin:
    def state(self: Any, *args: Any, **kwargs: Any) -> State:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in state() method should be set to the same simulation instance.')
        return State(*args, **kwargs, sim=sim)
