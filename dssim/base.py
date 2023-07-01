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
The base classes / intefaces / mixin for dssim framework.
'''
from __future__ import annotations
from abc import abstractmethod
from typing import Any, Dict, Tuple, List, Callable, Union, Optional, TYPE_CHECKING


NumericType = Union[float, int]

class DSAbsTime:
    ''' A class representing absolute time in the simulation '''
    def __init__(self, value: NumericType) -> None:
        self.value = value

    def to_number(self) -> NumericType:
        return self.value


TimeType = Union[DSAbsTime, float, int]


class DSEvent:
    ''' A base for events static typing. '''
    pass


EventType = Union[None, dict, Exception, DSEvent, Any,]
EventRetType = Optional[bool]


class ICondition:
    ''' An interface for a condition checkable classes '''
    @abstractmethod
    def check(self, event: EventType) -> Tuple[bool, Any]:
        raise NotImplementedError("The ICondition is an interface. Use derived class.")
    
    def __call__(self, event: EventType) -> Tuple[bool, Any]:
        return self.check(event)

CondType = Union[Callable, Any,]


class StackedCond(ICondition):
    ''' A condition which can stack several simple conditions '''

    def __init__(self) -> None:
        self.conds: list[Any] = []
        self.value = None

    def push(self, cond: Any) -> "StackedCond":
        ''' Adds new condition to the stack '''

        self.conds.append(cond)
        return self

    def pop(self) -> Any:
        ''' Removes last condition from the stack '''

        return self.conds.pop()

    def check_one(self, cond: CondType, event: EventType) -> Tuple[bool, Any]:
        ''' Checks one condition on the stack.
        
        :returns: a tuple (event_passed, value_of_event)
        '''

        # Check the event first
        # Instead of the following generic rule, it is better to add it as a stacked condition
        # for "None" value, it will be caught later by cond == event rule.
        # if event is None:  # timeout received
        #     return True, None
        if isinstance(event, Exception):  # any exception raised
            return True, event
        # Check the type of condition
        if cond == event:  # we are expecting exact event and it came
            return True, event
        elif isinstance(cond, ICondition):
            return cond.check(event)
        elif callable(cond) and cond(event):  # there was a filter function set and the condition is met
            return True, event
        else:  # the event does not match our condition and hence will be ignored
            return False, None
    
    def check(self, event: EventType) -> Tuple[bool, EventType]:
        ''' Checks the stack.
        The event is passed to all the conditions on the stack till it finds the first one
        which passes.
        
        :returns: a result of pass check- a tuple (event_passed, value_of_event)
        '''

        signaled, retval = False, event
        for cond in self.conds:
            signaled, event = self.check_one(cond, retval)
            if signaled:
                if hasattr(cond, 'cond_value'):
                    retval = cond.cond_value()
                else:
                    retval = event
                self.value = retval
                break
        return signaled, retval

    def cond_value(self) -> Any:
        ''' Gets a representation of last passed event
        
        :returns: a value of the last event which passed the check
        '''
        return self.value


class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, producer: Any = None, **info) -> None:
        super().__init__()
        self.producer = producer
        self.info = info


class DSTransferableCondition(ICondition):
    ''' A condition which can modify the event value '''

    def __init__(self, cond: CondType, transfer: Callable[[EventType], EventType] = lambda e:e) -> None:
        '''
        :param cond: The condition which is required to pass
        :param transfer: The callable which will be called when the check passes.
            The arg to the callable is the event. The return is the new value.
        '''
       
        self.cond = StackedCond().push(cond)
        self.transfer = transfer
        self.value = None

    def check(self, value):
        signaled, retval = self.cond.check(value)
        if signaled:
            retval = self.transfer(retval)
        return signaled, retval


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation  # to satisfy static analyzer


class DSComponentSingleton:
    ''' An extension for simulator to setup the first instance of the DSSimulation '''
    sim_singleton: Optional[DSSimulation] = None


class DSComponent:
    ''' DSComponent is any component which uses simulation (sim) environment.
    The component shall have assigned a simulation instance (useful when
    creating more simulation instances in one application).
    If the sim instance is not specified, the one from singleton will be assigned.

    The interface has a rule that every instance shall have a (unique) name
    (useful for debugging when debugger displays interface name).
    If the name is not specified, it is created from the simulation instance
    and class name.
    '''

    def __init__(self, *args, name: Optional[str] = None, sim: Optional[DSSimulation] = None, **kwargs) -> None:
        temp_name = name or f'{self.__class__}'
        # It is recommended that core components specify the sim argument, i.e. sim should not be None
        sim_candidate = sim or DSComponentSingleton.sim_singleton
        if sim_candidate is None:
            raise ValueError(f'Interface {temp_name} does not have sim parameter set and no DSSimulation was created yet.')
        self.sim = sim_candidate
        if name is None:
            name = temp_name
            counter = self.sim.names.get(name, 0)
            self.sim.names[name] = counter + 1
            name = name + f'{counter}'
        elif name in self.sim.names:
            raise ValueError(f'Interface with name {name} already registered in the simulation instance {self.sim.name}.')
        else:
            self.sim.names[name] = 0
        self.name = name

    def __repr__(self) -> str:
        return self.name


class DSStatefulComponent(DSComponent):
    ''' The base class which adds tx_changed endpoint which sends event
    upon a change of the component.
    '''
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tx_changed = self.sim.producer(name=self.name+'.tx')
    
    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=cond)
        return retval

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True) -> Generator[EventType, EventType, EventType]:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e:True) -> EventType:
        ''' Wait for change in the state and returns when the condition is met '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval


# In the following, self is in fact of type DSConsumer, but PyLance makes troubles with variable types
class SignalMixin:
    ''' Pairs of methods for extending a functionality of a consumer '''

    def signal(self: Any, event: EventType) -> EventType:
        ''' Signal event. '''
        return self.sim.signal(self, event)

    def signal_kw(self: Any, **event) -> EventType:
        ''' Signal key-value event type as kwargs. '''
        return self.sim.signal(self, event)

    def schedule_event(self: Any, time: TimeType, event: EventType) -> EventType:
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)

    def schedule_kw_event(self: Any, time: TimeType, **event) -> EventType:
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)
