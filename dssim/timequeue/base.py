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
Interface for simulation time-queue implementations.
'''

from abc import ABC, abstractmethod
from typing import Deque, Tuple, Union

from dssim.base import EventType, ISubscriber

TimeType = float
ElementType = Tuple[ISubscriber, Union[EventType, ISubscriber]]


class ITimeQueue(ABC):
    '''Interface implemented by simulation time-queue backends.'''

    @abstractmethod
    def add_element(self, time: TimeType, element: ElementType) -> None:
        pass

    @abstractmethod
    def get_first_time(self) -> TimeType:
        pass

    @abstractmethod
    def pop_first_bucket(self) -> Deque[ElementType]:
        pass

    @abstractmethod
    def insertleft(self, time: TimeType, events: Deque[ElementType]) -> None:
        pass

    @abstractmethod
    def delete_sub(self, sub: ISubscriber) -> None:
        pass

    @abstractmethod
    def delete_val(self, val: ElementType) -> None:
        pass

    @abstractmethod
    def event_count(self) -> int:
        pass

    @abstractmethod
    def __bool__(self) -> bool:
        pass
