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
from typing import Any, Optional, Callable, Generator
from abc import abstractmethod
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


class MethodBinder:
    ''' A structure encapsulating 3 functions.
    The functions are helpers to route a method from a class to another method.
    '''
    @staticmethod
    def bind(obj, name, wrapped):
        if obj is not None:
            cls = obj.__class__
            wrapper_bounded_with_instance = wrapped.__get__(obj, cls)
            setattr(obj, name, wrapper_bounded_with_instance)
        else:
            globals()[name] = wrapped

    @staticmethod
    def probed_generator(fcn: Callable, ep: DSProducer):
        ''' Wrapper which derives new methods adding probing functionality '''
        def probe_wrapper(self, *args, **kwargs) -> Any:
            retval = None
            t = self.sim.time
            try:
                ep.send({'op': 'enter', 'pid': self.sim.pid, 'time': self.sim.time})
                retval = yield from fcn(*args, **kwargs)
            except Exception as e:
                ep.send({'op': 'exit', 'pid': self.sim.pid, 'time': self.sim.time, 'event': e})
                raise
            ep.send({'op': 'exit', 'pid': self.sim.pid, 'time': self.sim.time, 'event': retval})
            return retval
        return probe_wrapper

    @staticmethod
    def probed_coroutine(fcn: Callable, ep: DSProducer):
        ''' Wrapper which derives new methods adding probing functionality '''
        async def probe_wrapper(self, *args, **kwargs) -> Any:
            retval = None
            t = self.sim.time
            try:
                ep.send({'op': 'enter', 'pid': self.sim.pid, 'time': self.sim.time})
                retval = await fcn(*args, **kwargs)
            except Exception as e:
                ep.send({'op': 'exit', 'pid': self.sim.pid, 'time': self.sim.time, 'event': e})
                raise
            ep.send({'op': 'exit', 'pid': self.sim.pid, 'time': self.sim.time, 'event': retval})
            return retval
        return probe_wrapper


class DSWaitableComponent(DSProbedComponent, DSStatefulComponent):
    ''' The base class which adds tx_changed endpoint which sends event
    upon a change of the component.
    '''
    def _set_loggers(self):
        super()._set_loggers()
        self.wait_ep = DSProducer(name=self.name+'.tx_wait')

    def _set_probed_methods(self):
        super()._set_probed_methods()
        MethodBinder.bind(self, 'check_and_gwait', MethodBinder.probed_generator(self.check_and_gwait, self.wait_ep))
        MethodBinder.bind(self, 'check_and_wait', MethodBinder.probed_coroutine(self.check_and_wait, self.wait_ep))
        MethodBinder.bind(self, 'gwait', MethodBinder.probed_generator(self.gwait, self.wait_ep))
        MethodBinder.bind(self, 'wait', MethodBinder.probed_coroutine(self.wait, self.wait_ep))
    
    def _set_unprobed_methods(self):
        super()._set_unprobed_methods()
        MethodBinder.bind(self, 'check_and_gwait', self.check_and_gwait)
        MethodBinder.bind(self, 'check_and_wait', self.check_and_wait)
        MethodBinder.bind(self, 'gwait', self.gwait)
        MethodBinder.bind(self, 'wait', self.wait)

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
 

