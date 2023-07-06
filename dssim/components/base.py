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
from abc import abstractmethod
from enum import Enum
from dssim.base import TimeType, CondType, EventType, DSComponent
from dssim.pubsub import DSProducer


class DSStatefulComponent(DSComponent):
    ''' The base abstract class which adds tx_changed endpoint which sends event
    upon a change of the component.
    The loggers and execution control for the probed methods should be defined in the derived class.
    '''
    def __init__(self, *args: Any, change_ep: Optional[DSProducer] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tx_changed = change_ep if change_ep is not None else self.sim.producer(name=self.name+'.tx')


class DSProbedComponent(DSComponent):
    def __init__(self, *args: Any, blocking_stat: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._set_loggers()
        if blocking_stat:
            self._set_probed_methods()
        else:
            self._set_unprobed_methods()

    @abstractmethod
    def _set_loggers(self): pass

    @abstractmethod
    def _set_probed_methods(self): pass
    
    @abstractmethod
    def _set_unprobed_methods(self): pass

    def probed_generator(self, fcn, logger):
        ''' Wrapper which derives new methods adding probing functionality '''
        def probe_wrapper(*args, **kwargs) -> Any:
            retval = None
            t = self.sim.time
            try:
                retval = yield from fcn(*args, **kwargs)
            finally:
                logger.append((self.sim.time - t, self.sim.pid))
            return retval
        return probe_wrapper

    def probed_coroutine(self, fcn, logger):
        ''' Wrapper which derives new methods adding probing functionality '''
        async def probe_wrapper(*args, **kwargs) -> Any:
            retval = None
            t = self.sim.time
            try:
                retval = await fcn(*args, **kwargs)
            finally:
                logger.append((self.sim.time - t, self.sim.pid))
            return retval
        return probe_wrapper


class DSWaitableComponent(DSStatefulComponent, DSProbedComponent):
    ''' The base class which adds tx_changed endpoint which sends event
    upon a change of the component.
    '''
    def _set_loggers(self):
        super()._set_loggers()
        self.wait_logger = []

    def _set_probed_methods(self):
        super()._set_probed_methods()
        self.check_and_gwait = self.probed_generator(self._check_and_gwait, self.wait_logger)
        self.check_and_wait = self.probed_coroutine(self._check_and_wait, self.wait_logger)
        self.gwait = self.probed_generator(self._gwait, self.wait_logger)
        self.wait = self.probed_coroutine(self._wait, self.wait_logger)
    
    def _set_unprobed_methods(self):
        super()._set_unprobed_methods()
        self.check_and_gwait = self._check_and_gwait
        self.check_and_wait = self._check_and_wait
        self.gwait = self._gwait
        self.wait = self._wait

    # from dssim.base import probing_fcns
    # @probing_fcns.create_probing_fcn('wait_logger', 'check_and_gwait')
    def _check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    # @create_probing_fcn('wait_logger', 'check_and_gwait')
    async def _check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=cond)
        return retval

    # @create_probing_fcn('wait_logger', 'gwait')
    def _gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    # @create_probing_fcn('wait_logger', 'wait')
    async def _wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True, **policy_params: Any) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval
 

