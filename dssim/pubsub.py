# Copyright 2020 NXP Semiconductors
# Copyright 2020- majvan (majvan@gmail.com)
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
This file defines publishers (producers) and subscribers (observers,
consumers or monitors).
Observer: an object which takes (snifss) signals from producers
Consumer: an object which takes signal from producer and then stops
  further spread.
'''
from abc import abstractmethod
from typing import List, Dict, Any, Type, Generator, Callable, Tuple, Iterator, TYPE_CHECKING
from dssim.base import TimeType, CondType, StackedCond, DSComponent, DSEvent, EventType, EventRetType, SignalMixin


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class ConsumerMetadata:
    def __init__(self):
        self.cond = StackedCond()


class DSTrackableEvent(DSEvent):
    ''' The class encapsulates an event and adds a trace log for producers '''

    def __init__(self, value: Any) -> None:
        self.value = value
        self.producers: List[DSProducer] = []

    def track(self, producer: "DSProducer") -> None:
        self.producers.append(producer)

    def __repr__(self) -> str:
        return f'DSTrackableEvent({self.value})'


def TrackEvent(fcn):
    ''' Wrapper (decorator) for methods which add new log into trackable event '''

    def api(self, event: EventType, *args, **kwargs) -> Any:
        if isinstance(event, DSTrackableEvent):
            event.producers.append(self)
        return fcn(self, event, *args, **kwargs)
    return api


class DSConsumer(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.create_metadata(**kwargs)
       
    def create_metadata(self, **kwargs) -> ConsumerMetadata:
        self.meta = ConsumerMetadata()
        if 'cond' in kwargs:
            self.meta.cond.push(kwargs['cond'])
        return self.meta

    def get_cond(self):
        return self.meta.cond

    @TrackEvent
    @abstractmethod
    def send(self, event):
        ''' Receive event. This interface should be used only by DSSimulator instance as
        the main dispatcher for directly sending messages.
        Bypassing DSSimulator by calling the consumer send() directly would bypass the
        condition check and could also result into dependency issues.
        The name 'send' is required as python's generator.send() is de-facto consumer, too.
        '''
        raise NotImplementedError('Abstract method, use derived classes')


class DSCallback(DSConsumer):
    ''' A callback interface.
    The callback interface is called from the simulator when a process sends events.
    '''
    def __init__(self, forward_method: Callable[..., EventType], cond: CondType = lambda e: True, **kwargs):
        super().__init__(cond=cond, **kwargs)
        self.forward_method = forward_method

    @TrackEvent
    def send(self, event: EventType):
        ''' The function calls the registered callback. '''
        retval = self.forward_method(event)
        return retval


class DSKWCallback(DSCallback):

    @TrackEvent
    def send(self, event: dict) -> EventType:
        ''' The function calls registered callback providing that the event is dict. '''
        retval = self.forward_method(**event)
        return retval
    

class VoidConsumer(DSConsumer):
    ''' A void consumer which should never be called.
    It is even not assigned to an simulation instance.
    The singleton instance of this consumer is used only to satisfy
    not-null consumer type requirements in some default functions
    to simplify the code.
    '''
    def __init__(self, *args, **kwargs) -> None:
        self.name: str = "Default source / consumer"

    def send(self, event: EventType) -> None:
        raise RuntimeError('A void consumer is never expected to be called.')

void_consumer = VoidConsumer()


class NotifierPolicy:
    @abstractmethod
    def __iter__(self) -> Iterator: ...

    @abstractmethod
    def rewind(self) -> None: ...

    @abstractmethod
    def inc(self, key: DSConsumer, **kwargs: Any) -> None: ...

    @abstractmethod
    def dec(self, key: DSConsumer, **kwargs: Any) -> None: ...

    @abstractmethod
    def cleanup(self) -> None: ...


NotifierTypeIter = Tuple[DSConsumer, int]
NotifierDictItemType = int
NotifierDictItemsType = Dict[DSConsumer, NotifierDictItemType]

class NotifierDict(NotifierPolicy):
    def __init__(self) -> None:
        self.d: NotifierDictItemsType = {}

    def __iter__(self) -> Iterator[NotifierTypeIter]:
        return iter(list(self.d.items()))

    def rewind(self) -> None:
        return

    def inc(self, key: DSConsumer, **kwargs: Any) -> None:
        self.d[key] = self.d.get(key, 0) + 1

    def dec(self, key: DSConsumer, **kwargs: Any) -> None:
        self.d[key] = self.d.get(key, 0) - 1

    def cleanup(self) -> None:
        old_dict = self.d
        new_dict = {k: v for k, v in old_dict.items() if v > 0}
        self.d = new_dict


class NotifierRoundRobinItem:
    def __init__(self, key: DSConsumer, value: int) -> None:
        self.key, self.value = key, value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return (self.key, self.value) == other
        elif isinstance(other, NotifierRoundRobinItem):
            return (self.key, self.value) == (other.key, other.value)
        else:
            raise NotImplementedError(f"Cannot compare {self} and {other}")


NotifierRRItemType = NotifierRoundRobinItem
NotifierRRItemsType = List[NotifierRoundRobinItem]

class NotifierRoundRobin(NotifierPolicy):
    def __init__(self) -> None:
        self.queue: NotifierRRItemsType = []

    def __iter__(self) -> "NotifierRoundRobin":
        self.current_index: int = 0
        self.max_index: int = len(self.queue)
        return self

    def __next__(self) -> NotifierTypeIter:
        if self.current_index >= self.max_index:
            raise StopIteration
        item = self.queue[self.current_index]
        self.current_index += 1
        return (item.key, item.value)

    def rewind(self) -> None:
        self.queue = self.queue[self.current_index:] + self.queue[:self.current_index:]

    def inc(self, key: DSConsumer, **kwargs: Any) -> None:
        for item in self.queue:
            if item.key == key:
                item.value += 1
                return
        self.queue.append(NotifierRoundRobinItem(key, 1))

    def dec(self, key: DSConsumer, **kwargs: Any) -> None:
        for item in self.queue:
            if item.key == key:
                item.value -= 1
                return
        raise ValueError('A key was supposed to be in the queue')

    def cleanup(self) -> None:
        new_queue = []
        for item in self.queue:
            if item.value > 0:
                new_queue.append(item)
        self.queue = new_queue


NotifierPriorityItemType = Tuple[int, Dict[DSConsumer, int]]
NotifierPriorityItemsType = Dict[int, Dict[DSConsumer, int]]
NotifierPriorityItemIter = Tuple[DSConsumer, int]

class NotifierPriority(NotifierPolicy):
    def __init__(self) -> None:
        self.d: NotifierPriorityItemsType = {}

    def __iter__(self) -> Any: #Iterator[NotifierPriorityItemType]:
        return iter(list(self._iterate_by_priority()))

    def _iterate_by_priority(self) -> Iterator[NotifierPriorityItemIter]:
        for prio in sorted(self.d.keys()):
            for d in self.d[prio].items():
                yield d

    def rewind(self) -> None:
        return

    def inc(self, key: DSConsumer, priority: int = 0, **kwargs: Any) -> None:
        priority_dict = self.d[priority] = self.d.get(priority, {})
        priority_dict[key] = priority_dict.get(key, 0) + 1

    def dec(self, key: DSConsumer, priority: int = 0, **kwargs: Any) -> None:
        priority_dict = self.d[priority] = self.d.get(priority, {})
        priority_dict[key] = priority_dict.get(key, 0) - 1

    def cleanup(self) -> None:
        new_prio_dict = {}
        for key, old_dict in self.d.items():
            new_dict = {k: v for k, v in old_dict.items() if v > 0}
            if new_dict:
                new_prio_dict[key] = new_dict
        self.d = new_prio_dict


class DSProducer(DSConsumer, SignalMixin):
    ''' Full feature producer which consumes signal events and resends it to the attached consumers. '''
    def __init__(self, notifier: Type[NotifierPolicy] = NotifierDict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.subs = {
            'pre': notifier(),
            'act': notifier(),
            'post+': notifier(),
            'post-': notifier(),
        }
        # A producer takes any event - no conditional
        self.meta.cond.push(lambda e: True)

    def add_subscriber(self, subscriber: DSConsumer, phase: str = 'act', **kwargs: Any) -> None:
        subs = self.subs[phase]
        subs.inc(subscriber, **kwargs)

    def remove_subscriber(self, subscriber: DSConsumer, phase: str = 'act', **kwargs: Any) -> None:
        subs = self.subs[phase]
        subs.dec(subscriber, **kwargs)

    @TrackEvent
    def send(self, event: EventType) -> None:
        ''' Send signal object to the subscribers '''

        # Emit the signal to all pre-observers
        for subscriber, refs in self.subs['pre']:
            if refs:
                self.sim.try_send(subscriber, event)

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        for consumer, refs in self.subs['act']:
            if refs and self.sim.try_send(consumer, event):
                # The event was consumed.
                self.subs['act'].rewind()  # this will rewind for round robin
                # Notify all the post-observers about consumed event.
                for subscriber, prefs in self.subs['post+']:
                    # The post-observers will receive a dict with two objects
                    if prefs:
                        self.sim.try_send(subscriber, {'consumer': consumer, 'event': event})
                break
        else:
            # Emit the missed signal to all post-observers
            for subscriber, refs in self.subs['post-']:
                if refs:
                    self.sim.try_send(subscriber, event)

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error 
        for queue in self.subs.values():
            queue.cleanup()

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: False, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        with self.sim.consume(self):
            retval = yield from self.sim.gwait(timeout, cond, val)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType =lambda e: False, val: EventRetType = True) -> EventType:
        with self.sim.consume(self):
            retval = await self.sim.wait(timeout, cond, val)
        return retval


class DSTransformation(DSProducer):
    ''' A producer which takes a signal, transforms / wraps it to another signal and
    sends to a consumer.
    The typical use case is to transform events from one endpoint to a process as exceptions.
    '''
    def __init__(self, ep: DSProducer, transformation: Callable[[EventType], EventType], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ep = ep
        self.transformation = transformation

    def add_subscriber(self, subscriber: DSConsumer, *args: Any, **kwargs: Any) -> None:
        self.ep.add_subscriber(self, *args, **kwargs)
        super().add_subscriber(subscriber, *args, **kwargs)
    
    def remove_subscriber(self, subscriber: DSConsumer, *args: Any, **kwargs: Any) -> None:
        self.ep.remove_subscriber(self, *args, **kwargs)
        super().remove_subscriber(subscriber, *args, **kwargs)

    @TrackEvent
    def send(self, event: EventType) -> None:
        event = self.transformation(event)
        super().send(event)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimPubsubMixin:
    def producer(self: Any, *args: Any, **kwargs: Any) -> DSProducer:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in producer() method should be set to the same simulation instance.')
        return DSProducer(*args, **kwargs, sim=sim)

    def callback(self: Any, *args: Any, **kwargs: Any) -> DSCallback:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in callback() method should be set to the same simulation instance.')
        return DSCallback(*args, **kwargs, sim=sim)

    def kw_callback(self: Any, *args: Any, **kwargs: Any) -> DSKWCallback:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in kw_callback() method should be set to the same simulation instance.')
        return DSKWCallback(*args, **kwargs, sim=sim)
