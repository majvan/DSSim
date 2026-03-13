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
Subscriber: anyone who gets events (objects) from publisher
Observer: the one which only observers the event (object)
Consumer: the one which has ability to take the event (object) and 'consume'
it => to gate rerouting it to other potential consumers
'''
from abc import abstractmethod
from enum import IntEnum
from bisect import bisect_left, insort
from typing import List, Dict, Any, Type, Generator, Callable, Tuple, Iterator, TYPE_CHECKING
from dssim.base import TimeType, DSComponent, DSEvent, EventType, SignalMixin, ISubscriber
from dssim.pubsub.base import CondType, AlwaysTrue, SubscriberMetadata, StackedCond


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSTrackableEvent(DSEvent):
    ''' The class encapsulates an event and adds a trace log for publishers. '''

    def __init__(self, value: Any) -> None:
        self.value = value
        self.publishers: List[DSPub] = []

    def track(self, publisher: "DSPub") -> None:
        self.publishers.append(publisher)

    def __repr__(self) -> str:
        return f'DSTrackableEvent({self.value})'


def TrackEvent(fcn):
    ''' Wrapper (decorator) for methods which add new log into trackable event '''

    def api(self, event: EventType, *args, **kwargs) -> Any:
        if isinstance(event, DSTrackableEvent):
            event.publishers.append(self)
        return fcn(self, event, *args, **kwargs)
    return api


class DSSub(DSComponent, ISubscriber):
    # Plain subscribers are direct-send capable by default.
    supports_direct_send: bool = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_metadata(**kwargs)
       
    def create_metadata(self, **kwargs) -> SubscriberMetadata:
        self.meta = SubscriberMetadata()
        return self.meta

    @TrackEvent
    @abstractmethod
    def send(self, event):
        ''' Receive event. This interface should be used only by DSSimulator instance as
        the main dispatcher for directly sending messages.
        Bypassing DSSimulator by calling the subscriber send() directly would bypass the
        condition check and could also result into dependency issues.
        The name 'send' is required as python's generator.send() is de-facto subscriber, too.
        '''
        raise NotImplementedError('Abstract method, use derived classes')


class DSCondSub(DSComponent, ISubscriber):
    # Condition-aware subscribers can still be direct-send capable when
    # configured with an unconditional predicate.
    supports_direct_send: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.create_metadata(**kwargs)

    def create_metadata(self, **kwargs) -> SubscriberMetadata:
        self.meta = SubscriberMetadata()
        if 'cond' in kwargs:
            cond = kwargs['cond']
            self.meta.cond.push(cond)
        return self.meta

    def get_cond(self):
        return self.meta.cond

    def reset_cond(self) -> None:
        self.meta.cond = StackedCond()

    def try_send(self, event: EventType) -> EventType:
        ''' Send an event to this subscriber if its condition is met. Returns False if not accepted. '''
        conds = self.meta.cond
        signaled, event = conds.check(event)
        if not signaled:
            return False
        return self.sim.send_object(self, event)

    @TrackEvent
    @abstractmethod
    def send(self, event):
        raise NotImplementedError('Abstract method, use derived classes')


class DSCallback(DSSub):
    ''' A callback interface.
    The callback interface is called from the simulator when a process sends events.
    '''
    supports_direct_send: bool = True

    def __init__(self, forward_method: Callable[..., EventType], **kwargs):
        if 'cond' in kwargs:
            raise TypeError('DSCallback is condition-unaware; use DSCondCallback for conditioned callbacks.')
        super().__init__(**kwargs)
        self.forward_method = forward_method

    @TrackEvent
    def send(self, event: EventType):
        ''' The function calls the registered callback. '''
        retval = self.forward_method(event)
        return retval


class DSKWCallback(DSCallback):
    supports_direct_send: bool = True

    @TrackEvent
    def send(self, event: dict) -> EventType:
        ''' The function calls registered callback providing that the event is dict. '''
        retval = self.forward_method(**event)
        return retval


class DSCondCallback(DSCondSub):
    supports_direct_send: bool = False

    def __init__(self, forward_method: Callable[..., EventType], cond: CondType = AlwaysTrue, **kwargs):
        super().__init__(cond=cond, **kwargs)
        self.forward_method = forward_method

    @TrackEvent
    def send(self, event: EventType):
        retval = self.forward_method(event)
        return retval


class DSKWCondCallback(DSCondCallback):
    supports_direct_send: bool = False

    @TrackEvent
    def send(self, event: dict) -> EventType:
        retval = self.forward_method(**event)
        return retval


class NotifierPolicy:
    needs_cleanup: bool = False  # overridden to True by dec() in subclasses that defer removal

    @abstractmethod
    def __iter__(self) -> Iterator: ...

    @abstractmethod
    def rewind(self) -> None: ...

    @abstractmethod
    def inc(self, key: ISubscriber, **policy_params: Any) -> None: ...

    @abstractmethod
    def dec(self, key: ISubscriber, **policy_params: Any) -> None: ...

    @abstractmethod
    def cleanup(self) -> None: ...


NotifierTypeIter = Tuple[ISubscriber, int]
NotifierDictItemType = int
NotifierDictItemsType = Dict[ISubscriber, NotifierDictItemType]

class NotifierDict(NotifierPolicy):
    def __init__(self) -> None:
        self.d: NotifierDictItemsType = {}

    def __iter__(self) -> Iterator[NotifierTypeIter]:
        return iter(list(self.d.items()))

    def rewind(self) -> None:
        return

    def inc(self, key: ISubscriber, **kwargs: Any) -> None:
        self.d[key] = self.d.get(key, 0) + 1

    def dec(self, key: ISubscriber, **kwargs: Any) -> None:
        v = self.d.get(key, 0) - 1
        if v <= 0:
            self.d.pop(key, None)  # remove immediately; __iter__ uses a list() snapshot so this is safe
        else:
            self.d[key] = v

    def cleanup(self) -> None:
        pass  # dec() already removes zero-count entries inline


class NotifierRoundRobinItem:
    def __init__(self, key: ISubscriber, value: int) -> None:
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
        self.needs_cleanup: bool = False

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

    def inc(self, key: ISubscriber, **kwargs: Any) -> None:
        for item in self.queue:
            if item.key == key:
                item.value += 1
                return
        self.queue.append(NotifierRoundRobinItem(key, 1))

    def dec(self, key: ISubscriber, **kwargs: Any) -> None:
        for item in self.queue:
            if item.key == key:
                item.value -= 1
                if item.value <= 0:
                    self.needs_cleanup = True
                return
        raise ValueError('A key was supposed to be in the queue')

    def cleanup(self) -> None:
        self.needs_cleanup = False
        self.queue = [item for item in self.queue if item.value > 0]


NotifierPriorityItemType = Tuple[int, Dict[ISubscriber, int]]
NotifierPriorityItemsType = Dict[int, Dict[ISubscriber, int]]
NotifierPriorityItemIter = Tuple[ISubscriber, int]

class NotifierPriority(NotifierPolicy):
    def __init__(self) -> None:
        self.d: NotifierPriorityItemsType = {}
        self._sorted_priorities: List[int] = []
        self._dict_id: int = id(self.d)
        self.needs_cleanup: bool = False

    def __iter__(self) -> Iterator[NotifierPriorityItemIter]:
        # Freeze priority ordering for this iteration, but snapshot each
        # priority bucket lazily so callers that break early avoid flattening
        # all buckets into one list.
        priorities = tuple(self._get_sorted_priorities())
        d = self.d
        for prio in priorities:
            bucket = d.get(prio)
            if not bucket:
                continue
            for item in list(bucket.items()):
                yield item

    def _get_sorted_priorities(self) -> List[int]:
        # Defensive invalidation: tests and advanced callers may replace
        # self.d directly (without inc/dec), so we track dict identity too.
        if self.needs_cleanup or self._dict_id != id(self.d):
            self._sorted_priorities = sorted(self.d.keys())
            self._dict_id = id(self.d)
        return self._sorted_priorities

    def rewind(self) -> None:
        return

    def inc(self, key: ISubscriber, priority: int = 0, **kwargs: Any) -> None:
        if priority not in self.d:
            self.d[priority] = {}
            insort(self._sorted_priorities, priority)
        priority_dict = self.d[priority]
        priority_dict[key] = priority_dict.get(key, 0) + 1

    def dec(self, key: ISubscriber, priority: int = 0, **kwargs: Any) -> None:
        priority_dict = self.d.get(priority)
        if priority_dict is None:
            self.d[priority] = {}
            priority_dict = self.d[priority]
        v = priority_dict.get(key, 0) - 1
        if v <= 0:
            priority_dict.pop(key, None)
            if not priority_dict:
                self.d.pop(priority, None)
                idx = bisect_left(self._sorted_priorities, priority)
                if idx < len(self._sorted_priorities) and self._sorted_priorities[idx] == priority:
                    self._sorted_priorities.pop(idx)
        else:
            priority_dict[key] = v

    def cleanup(self) -> None:
        # Keep sorted-priority cache coherent with current keys when d was
        # externally replaced and clear deferred cleanup flag.
        self._get_sorted_priorities()
        self.needs_cleanup = False


class DSPub(DSSub, SignalMixin):
    ''' Full feature publisher which forwards signal events to attached subscribers. '''

    class Phase(IntEnum):
        PRE = 0
        CONSUME = 1
        POST_HIT = 2   # event was consumed
        POST_MISS = 3  # event was not consumed

    def __init__(self, notifier: Type[NotifierPolicy] = NotifierDict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.subs = (notifier(), notifier(), notifier(), notifier())
        self._subscriber_count = 0  # total ref-count across all tiers; kept in sync by add/remove_subscriber
        self._phase_subscriber_count = [0, 0, 0, 0]
        # A publisher takes any event - no conditional
        self.meta.cond.push(AlwaysTrue)

    def add_subscriber(self, subscriber: ISubscriber, phase: Phase = Phase.CONSUME, **kwargs: Any) -> None:
        self.subs[phase].inc(subscriber, **kwargs)
        self._subscriber_count += 1
        self._phase_subscriber_count[phase] += 1

    def remove_subscriber(self, subscriber: ISubscriber, phase: Phase = Phase.CONSUME, **kwargs: Any) -> None:
        self.subs[phase].dec(subscriber, **kwargs)
        self._subscriber_count -= 1
        self._phase_subscriber_count[phase] -= 1

    @TrackEvent
    def send(self, event: EventType) -> None:
        ''' Send signal object to the subscribers '''
        if self._subscriber_count <= 0:
            return

        pre, consume, post_hit, post_miss = self.subs
        pre_count, consume_count, post_hit_count, post_miss_count = self._phase_subscriber_count

        # Emit the signal to all pre-observers
        if pre_count > 0:
            for subscriber, refs in pre:
                if refs:
                    if subscriber.supports_direct_send:
                        subscriber.send(event)
                    else:
                        subscriber.try_send(event)

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        consumed = False
        accepted_consumer = None
        if consume_count > 0:
            for consumer, refs in consume:
                if refs:
                    if consumer.supports_direct_send:
                        retval = consumer.send(event)
                    else:
                        retval = consumer.try_send(event)
                    if retval:
                        consumed = True
                        accepted_consumer = consumer
                        # The event was consumed.
                        consume.rewind()  # this will rewind for round robin
                        break
        if consumed:
            # Notify all the post-observers about consumed event.
            if post_hit_count > 0:
                hit_payload = {'consumer': accepted_consumer, 'event': event}
                for subscriber, prefs in post_hit:
                    # The post-observers will receive a dict with two objects
                    if prefs:
                        if subscriber.supports_direct_send:
                            subscriber.send(hit_payload)
                        else:
                            subscriber.try_send(hit_payload)
        else:
            # Emit the missed signal to all post-observers
            if post_miss_count > 0:
                for subscriber, refs in post_miss:
                    if refs:
                        if subscriber.supports_direct_send:
                            subscriber.send(event)
                        else:
                            subscriber.try_send(event)

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error
        # Pre-check all for faster computation in hot path
        if pre.needs_cleanup or consume.needs_cleanup or post_hit.needs_cleanup or post_miss.needs_cleanup:
            if pre.needs_cleanup:
                pre.cleanup()
            if consume.needs_cleanup:
                consume.cleanup()
            if post_hit.needs_cleanup:
                post_hit.cleanup()
            if post_miss.needs_cleanup:
                post_miss.cleanup()

    def has_subscribers(self) -> bool:
        '''Returns True if any subscriber is attached in any tier (pre, consume, post+, post-).
        O(1) — backed by a cached ref-count maintained by add_subscriber / remove_subscriber.
        '''
        return self._subscriber_count > 0


class DSTransformation(DSPub):
    ''' A publisher which takes a signal, transforms / wraps it to another signal and
    sends to a subscriber.
    The typical use case is to transform events from one endpoint to a process as exceptions.
    '''
    def __init__(self, ep: DSPub, transformation: Callable[[EventType], EventType], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ep = ep
        self.transformation = transformation

    def add_subscriber(self, subscriber: DSSub, *args: Any, **kwargs: Any) -> None:
        self.ep.add_subscriber(self, *args, **kwargs)
        super().add_subscriber(subscriber, *args, **kwargs)
    
    def remove_subscriber(self, subscriber: DSSub, *args: Any, **kwargs: Any) -> None:
        self.ep.remove_subscriber(self, *args, **kwargs)
        super().remove_subscriber(subscriber, *args, **kwargs)

    @TrackEvent
    def send(self, event: EventType) -> None:
        event = self.transformation(event)
        super().send(event)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimPubsubMixin:
    def try_send_object(self: Any, subscriber: ISubscriber, event: EventType) -> EventType:
        '''PubSubLayer2 condition-aware dispatch used by DSSimulation.run().

        Pubsub subscribers may carry stacked conditions. Events that do not
        pass subscriber conditions must be filtered before delivery, therefore
        this layer wires a custom pre-check try_send_object into DSSimulation.
        '''
        if hasattr(subscriber, 'get_cond'):
            conds = subscriber.get_cond()
            signaled, event = conds.check(event)
            if not signaled:
                return False
        return self.send_object(subscriber, event)

    def publisher(self: Any, *args: Any, **kwargs: Any) -> DSPub:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in publisher() method should be set to the same simulation instance.')
        return DSPub(*args, **kwargs, sim=sim)

    def callback(self: Any, *args: Any, **kwargs: Any) -> "DSCallback | DSCondCallback":
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in callback() method should be set to the same simulation instance.')
        cond = kwargs.pop('cond', None)
        if cond is None:
            return DSCallback(*args, **kwargs, sim=sim)
        return DSCondCallback(*args, cond=cond, **kwargs, sim=sim)

    def kw_callback(self: Any, *args: Any, **kwargs: Any) -> "DSKWCallback | DSKWCondCallback":
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in kw_callback() method should be set to the same simulation instance.')
        cond = kwargs.pop('cond', None)
        if cond is None:
            return DSKWCallback(*args, **kwargs, sim=sim)
        return DSKWCondCallback(*args, cond=cond, **kwargs, sim=sim)
