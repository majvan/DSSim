# Copyright 2023- majvan (majvan@gmail.com)
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
The provides basic classes for the components.
'''
from typing import Any, Optional, Generator
from dssim.base import TimeType, CondType, EventType, DSComponent
from dssim.pubsub import DSProducer


class DSStatefulComponent(DSComponent):
    ''' The base class which adds tx_changed endpoint which sends event
    upon a change of the component.
    '''
    def __init__(self, change_ep: Optional[DSProducer] = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tx_changed = change_ep if change_ep is not None else self.sim.producer(name=self.name+'.tx')
    
    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=cond)
        return retval

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval
