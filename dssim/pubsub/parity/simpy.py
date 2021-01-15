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
Lightweight SimPy-style parity API on top of DSSim.

This module intentionally implements a practical subset commonly used in
examples:
- Environment / now / process() / timeout() / event() / run()
- Event / Process / AnyOf / AllOf
- Resource / PriorityResource / PreemptiveResource
- Store / FilterStore / PriorityStore

Scope note:
This is API-parity-oriented (for migration/examples), not a byte-for-byte
behavioral clone of SimPy internals.
'''
from __future__ import annotations

import heapq
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from dssim.base import ISubscriber
from dssim.simulation import DSSimulation


class Interrupt(Exception):
    '''SimPy-like process interruption exception.'''

    def __init__(self, cause: Any = None) -> None:
        super().__init__(cause)
        self.cause = cause


class Event:
    '''Basic SimPy-like event with callbacks and succeed/fail lifecycle.'''

    def __init__(self, env: 'Environment') -> None:
        self.env = env
        self.triggered = False
        self.processed = False
        self.ok = True
        self.value: Any = None
        self._exception: Optional[BaseException] = None
        self._callbacks: List[Callable[['Event'], None]] = []

    @property
    def exception(self) -> Optional[BaseException]:
        return self._exception

    def add_callback(self, callback: Callable[['Event'], None]) -> None:
        if self.triggered:
            callback(self)
            return
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[['Event'], None]) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def succeed(self, value: Any = None) -> 'Event':
        if self.triggered:
            return self
        self.triggered = True
        self.ok = True
        self.value = value
        self._dispatch()
        return self

    def fail(self, exception: BaseException) -> 'Event':
        if self.triggered:
            return self
        self.triggered = True
        self.ok = False
        self._exception = exception
        self._dispatch()
        return self

    def _dispatch(self) -> None:
        # Enable env.run(until=<event>) fast-stop by placing this event
        # into the simulation queue as an immediate marker.
        self.env.signal(self, self.env._event_probe)
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(self)
        self.processed = True

    def __or__(self, other: 'Event') -> 'AnyOf':
        return self.env.any_of([self, other])

    def __and__(self, other: 'Event') -> 'AllOf':
        return self.env.all_of([self, other])


class _NoOpSubscriber(ISubscriber):
    def send(self, event: Any) -> None:
        return None


class Timeout(Event, ISubscriber):
    '''Event that succeeds after a simulation delay.'''

    def __init__(self, env: 'Environment', delay: Any, value: Any = None) -> None:
        super().__init__(env)
        self._timeout_value = value
        self.env.schedule_event(delay, None, self)

    def send(self, event: Any) -> None:
        self.succeed(self._timeout_value)
        return None


class _ProcessResume:
    def __init__(self, value: Any) -> None:
        self.value = value


class _ProcessThrow:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


class Process(Event, ISubscriber):
    '''SimPy-like process event wrapping a generator/coroutine schedulable.'''

    def __init__(self, env: 'Environment', generator: Any) -> None:
        if not (inspect.isgenerator(generator) or inspect.iscoroutine(generator)):
            raise TypeError(f'process() expects generator/coroutine object, got {generator!r}')
        super().__init__(env)
        self._generator = generator
        self._waiting_event: Optional[Event] = None
        self._waiting_callback: Optional[Callable[[Event], None]] = None
        self.env.schedule_event(0, _ProcessResume(None), self)

    @property
    def is_alive(self) -> bool:
        return not self.triggered

    @property
    def target(self) -> Optional[Event]:
        return self._waiting_event

    def interrupt(self, cause: Any = None) -> None:
        if self.triggered:
            raise RuntimeError(f'{self} has terminated and cannot be interrupted.')
        self._detach_waiting(cancel_request=True)
        self.env.signal(_ProcessThrow(Interrupt(cause)), self)

    def _detach_waiting(self, cancel_request: bool) -> None:
        event = self._waiting_event
        callback = self._waiting_callback
        self._waiting_event = None
        self._waiting_callback = None
        if event is not None and callback is not None:
            event.remove_callback(callback)
            if cancel_request and hasattr(event, 'cancel'):
                event.cancel()

    def _resume_from_event(self, event: Event) -> None:
        self._detach_waiting(cancel_request=False)
        payload: Any
        if event.ok:
            payload = _ProcessResume(event.value)
        else:
            payload = _ProcessThrow(event.exception or RuntimeError('Event failed.'))
        self.env.signal(payload, self)

    def send(self, event: Any) -> Optional[Event]:
        if self.triggered:
            return None

        previous = self.env.active_process
        self.env.active_process = self
        try:
            try:
                if isinstance(event, _ProcessThrow):
                    yielded = self._generator.throw(event.exc)
                elif isinstance(event, _ProcessResume):
                    yielded = self._generator.send(event.value)
                else:
                    yielded = self._generator.send(event)
            except StopIteration as exc:
                self.succeed(exc.value)
                return None
            except BaseException as exc:  # pragma: no cover - guard path
                self.fail(exc)
                return None
        finally:
            self.env.active_process = previous

        if not isinstance(yielded, Event):
            self.fail(TypeError(f'Process yielded non-Event object: {yielded!r}'))
            return None

        if yielded.triggered:
            self._resume_from_event(yielded)
        else:
            self._waiting_event = yielded
            self._waiting_callback = self._resume_from_event
            yielded.add_callback(self._resume_from_event)
        return yielded


class _Condition(Event):
    def __init__(self, env: 'Environment', events: Iterable[Event]) -> None:
        super().__init__(env)
        self._events = list(events)
        self._results: Dict[Event, Any] = {}
        self._callbacks_by_event: Dict[Event, Callable[[Event], None]] = {}
        if not self._events:
            self.succeed({})
            return
        for event in self._events:
            callback = self._make_callback(event)
            self._callbacks_by_event[event] = callback
            event.add_callback(callback)

    def _make_callback(self, source: Event) -> Callable[[Event], None]:
        def _cb(event: Event) -> None:
            if self.triggered:
                return
            if event.ok:
                self._results[source] = event.value
                self._on_success(event)
            else:
                self._finalize()
                self.fail(event.exception or RuntimeError('Condition input failed.'))
        return _cb

    def _finalize(self) -> None:
        for event, callback in self._callbacks_by_event.items():
            event.remove_callback(callback)
        self._callbacks_by_event.clear()

    def _on_success(self, event: Event) -> None:
        raise NotImplementedError


class AnyOf(_Condition):
    def _on_success(self, event: Event) -> None:
        self._finalize()
        self.succeed(dict(self._results))


class AllOf(_Condition):
    def _on_success(self, event: Event) -> None:
        if len(self._results) == len(self._events):
            self._finalize()
            self.succeed(dict(self._results))


class Environment(DSSimulation):
    '''SimPy-like environment facade built on DSSimulation.'''

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Use base simulation only; layer2 mixins would override process()/wait
        # with pubsub/DSProcess behavior and break SimPy-style event yielding.
        kwargs.pop('layer2', None)
        super().__init__(*args, layer2=[], **kwargs)
        self.active_process: Optional[Process] = None
        self._event_probe = _NoOpSubscriber()

    @property
    def now(self) -> Any:
        return self.time

    def process(self, generator: Any) -> Process:
        return Process(self, generator)

    def timeout(self, delay: Any, value: Any = None) -> Timeout:
        return Timeout(self, delay, value)

    def event(self) -> Event:
        return Event(self)

    def any_of(self, events: Iterable[Event]) -> AnyOf:
        return AnyOf(self, events)

    def all_of(self, events: Iterable[Event]) -> AllOf:
        return AllOf(self, events)

    def run(self, until: Any = None):  # type: ignore[override]
        if until is None:
            return super().run()
        if isinstance(until, Event):
            return super().run(future=until)
        return super().run(until=until)


@dataclass
class Preempted:
    by: Optional[Process]
    usage_since: Optional[Any]
    resource: Any


class Request(Event):
    '''Resource request event, usable as context manager.'''

    def __init__(self, resource: 'Resource', proc: Optional[Process], priority: int, preempt: bool) -> None:
        super().__init__(resource.env)
        self.resource = resource
        self.proc = proc
        self.priority = priority
        self.preempt = preempt
        self.usage_since: Optional[Any] = None
        self._seq = -1

    def cancel(self) -> None:
        self.resource._cancel_request(self)

    def __enter__(self) -> 'Request':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.resource.release(self)


class Resource:
    '''SimPy-like Resource with request/release semantics.'''

    def __init__(self, env: Environment, capacity: int = 1) -> None:
        if capacity <= 0:
            raise ValueError('Resource capacity must be > 0.')
        self.env = env
        self.capacity = capacity
        self.users: List[Request] = []
        self.queue: List[Request] = []
        self.put_queue = self.queue
        self.get_queue: List[Any] = []

    def request(self, *, priority: int = 0, preempt: bool = False) -> Request:
        request = Request(self, self.env.active_process, priority=priority, preempt=preempt)
        self._enqueue_request(request)
        self._trigger()
        return request

    def release(self, request: Request) -> Event:
        released = False
        if request in self.users:
            self.users.remove(request)
            released = True
        elif request in self.queue:
            self.queue.remove(request)
            released = True
        if released:
            self._trigger()
        return self.env.event().succeed(True)

    def _cancel_request(self, request: Request) -> None:
        if request in self.queue:
            self.queue.remove(request)

    def _enqueue_request(self, request: Request) -> None:
        self.queue.append(request)

    def _dequeue_next(self) -> Request:
        return self.queue.pop(0)

    def _grant(self, request: Request) -> None:
        request.usage_since = self.env.now
        self.users.append(request)
        request.succeed(request)

    def _trigger(self) -> None:
        while self.queue and len(self.users) < self.capacity:
            request = self._dequeue_next()
            self._grant(request)


class PriorityResource(Resource):
    '''Resource variant selecting lowest numeric priority first.'''

    def __init__(self, env: Environment, capacity: int = 1) -> None:
        super().__init__(env, capacity=capacity)
        self._seq = 0

    def _enqueue_request(self, request: Request) -> None:
        request._seq = self._seq
        self._seq += 1
        self.queue.append(request)
        self.queue.sort(key=lambda req: (req.priority, req._seq))


class PreemptiveResource(PriorityResource):
    '''PriorityResource that can interrupt lower-priority current users.'''

    def _trigger(self) -> None:
        if self.queue and len(self.users) >= self.capacity:
            candidate = self.queue[0]
            if candidate.preempt:
                weakest = max(self.users, key=lambda req: (req.priority, req._seq))
                if (weakest.priority, weakest._seq) > (candidate.priority, candidate._seq):
                    self.users.remove(weakest)
                    if weakest.proc is not None:
                        weakest.proc.interrupt(Preempted(by=candidate.proc, usage_since=weakest.usage_since, resource=self))
        super()._trigger()


class StorePut(Event):
    def __init__(self, store: 'Store', item: Any) -> None:
        super().__init__(store.env)
        self.store = store
        self.item = item

    def cancel(self) -> None:
        try:
            self.store.put_queue.remove(self)
        except ValueError:
            pass


class StoreGet(Event):
    def __init__(self, store: 'Store', filter: Optional[Callable[[Any], bool]] = None) -> None:
        super().__init__(store.env)
        self.store = store
        self.filter = filter

    def cancel(self) -> None:
        try:
            self.store.get_queue.remove(self)
        except ValueError:
            pass


class Store:
    '''SimPy-like Store with put/get events.'''

    def __init__(self, env: Environment, capacity: int = float('inf')) -> None:
        self.env = env
        self.capacity = capacity
        self.items: List[Any] = []
        self.put_queue: List[StorePut] = []
        self.get_queue: List[StoreGet] = []

    def put(self, item: Any) -> StorePut:
        put_event = StorePut(self, item)
        self.put_queue.append(put_event)
        self._trigger()
        return put_event

    def get(self) -> StoreGet:
        get_event = StoreGet(self)
        self.get_queue.append(get_event)
        self._trigger()
        return get_event

    def _pop_matching_item(self, get_event: StoreGet) -> tuple[bool, Any]:
        if get_event.filter is None:
            if self.items:
                return True, self.items.pop(0)
            return False, None
        for index, item in enumerate(self.items):
            if get_event.filter(item):
                return True, self.items.pop(index)
        return False, None

    def _trigger(self) -> None:
        progressed = True
        while progressed:
            progressed = False

            # Serve waiting getters first from existing items.
            for get_event in list(self.get_queue):
                matched, item = self._pop_matching_item(get_event)
                if matched:
                    self.get_queue.remove(get_event)
                    get_event.succeed(item)
                    progressed = True

            # Move queued puts into items while capacity permits.
            while self.put_queue and len(self.items) < self.capacity:
                put_event = self.put_queue.pop(0)
                self.items.append(put_event.item)
                put_event.succeed(None)
                progressed = True

            # Try getters again after new puts.
            for get_event in list(self.get_queue):
                matched, item = self._pop_matching_item(get_event)
                if matched:
                    self.get_queue.remove(get_event)
                    get_event.succeed(item)
                    progressed = True


class FilterStore(Store):
    def get(self, filter: Callable[[Any], bool] = lambda item: True) -> StoreGet:
        get_event = StoreGet(self, filter=filter)
        self.get_queue.append(get_event)
        self._trigger()
        return get_event


class PriorityStore(Store):
    '''Store variant returning lowest-priority item first (heap semantics).'''

    def _pop_matching_item(self, get_event: StoreGet) -> tuple[bool, Any]:
        if get_event.filter is None:
            if self.items:
                return True, heapq.heappop(self.items)
            return False, None
        # Fallback path for filtered retrieval over heap items.
        # Keeps correctness; complexity is acceptable for parity usage.
        for index, item in enumerate(self.items):
            if get_event.filter(item):
                self.items[index] = self.items[-1]
                self.items.pop()
                if self.items:
                    heapq.heapify(self.items)
                return True, item
        return False, None

    def _trigger(self) -> None:
        progressed = True
        while progressed:
            progressed = False

            for get_event in list(self.get_queue):
                matched, item = self._pop_matching_item(get_event)
                if matched:
                    self.get_queue.remove(get_event)
                    get_event.succeed(item)
                    progressed = True

            while self.put_queue and len(self.items) < self.capacity:
                put_event = self.put_queue.pop(0)
                heapq.heappush(self.items, put_event.item)
                put_event.succeed(None)
                progressed = True

            for get_event in list(self.get_queue):
                matched, item = self._pop_matching_item(get_event)
                if matched:
                    self.get_queue.remove(get_event)
                    get_event.succeed(item)
                    progressed = True


__all__ = [
    'AllOf',
    'AnyOf',
    'Environment',
    'Event',
    'FilterStore',
    'Interrupt',
    'Preempted',
    'PreemptiveResource',
    'PriorityResource',
    'PriorityStore',
    'Process',
    'Request',
    'Resource',
    'Store',
    'Timeout',
]
