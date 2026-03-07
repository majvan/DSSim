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
from abc import ABC, abstractmethod
from typing import Any, Tuple, Callable, Union, Optional, Generator, TYPE_CHECKING


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


class ISubscriber(ABC):
    ''' Minimal interface for objects that receive simulation events.
    Pure-Python generators satisfy this interface via their built-in send(). '''	
    @abstractmethod
    def send(self, event: EventType) -> EventRetType: ...


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


# In the following, self is in fact of type DSConsumer, but PyLance makes troubles with variable types
class SignalMixin:
    ''' Pairs of helper methods for extending a functionality of a consumer.
    For better performance, it is recommended to avoid these helper methods
    and call the underlying DSSimulation methods directly.
    '''

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
