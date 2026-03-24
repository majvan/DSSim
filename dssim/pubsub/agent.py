# Copyright 2022- majvan (majvan@gmail.com)
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
The file provides process-centric API to easy the design of process-oriented
application.
'''
from abc import abstractmethod
from typing import Any, Optional, Generator, Type, Callable
import inspect
from dssim.base import EventType, TimeType, DSComponent, NumericType
from dssim.pubsub.base import CondType, DSAbortException, AlwaysTrue
from dssim.pubsub.process import DSProcess
from dssim.pubsub.pubsub import DSPub
from dssim.pubsub.agent_probes import AgentProbeMixin
from dssim.simulation import DSSchedulable
from dssim.pubsub.components.container import DSContainer
from dssim.pubsub.components.resource import DSResource


class AgentContainerMixin:
    async def enter(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> EventType:
        try:
            retval = await container.put(timeout, self, **policy_params)
        except DSAbortException:
            self.tx_changed.has_subscribers() and self._fire_changed('enter_abort', container=container, timeout=timeout)
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('enter', container=container, timeout=timeout, success=(retval is not None), result=retval)
        return retval

    def genter(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gput(timeout, self, **policy_params)
        except DSAbortException:
            self.tx_changed.has_subscribers() and self._fire_changed('genter_abort', container=container, timeout=timeout)
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('genter', container=container, timeout=timeout, success=(retval is not None), result=retval)
        return retval

    def enter_nowait(self: Any, container: DSContainer) -> Optional[EventType]:
        retval = container.put_nowait(self)
        self.tx_changed.has_subscribers() and self._fire_changed('enter_nowait', container=container, success=(retval is not None), result=retval)
        return retval

    def leave(self: Any, container: DSContainer) -> None:
        should_fire = self.tx_changed.has_subscribers()
        size_before = len(container) if should_fire and hasattr(container, '__len__') else None
        container.remove(self)
        if should_fire:
            if size_before is None:
                success = True
            else:
                success = len(container) < size_before
            self._fire_changed('leave', container=container, success=success)

    async def pop(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[EventType]:
        try:
            retval = await container.get(timeout, **policy_params)
        except DSAbortException:
            self.tx_changed.has_subscribers() and self._fire_changed('pop_abort', container=container, timeout=timeout)
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('pop', container=container, timeout=timeout, success=(retval is not None), result=retval)
        return retval

    def gpop(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gget(timeout, **policy_params)
        except DSAbortException:
            self.tx_changed.has_subscribers() and self._fire_changed('gpop_abort', container=container, timeout=timeout)
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('gpop', container=container, timeout=timeout, success=(retval is not None), result=retval)
        return retval

    def pop_nowait(self: Any, container: DSContainer) -> Optional[EventType]:
        retval = container.get_nowait()
        self.tx_changed.has_subscribers() and self._fire_changed('pop_nowait', container=container, success=(retval is not None), result=retval)
        return retval


class AgentResourceMixin:
    async def get(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.get(timeout, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('get', resource=resource, timeout=timeout, success=bool(retval), amount=retval)
        return retval

    def gget(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gget(timeout, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('gget', resource=resource, timeout=timeout, success=bool(retval), amount=retval)
        return retval

    async def get_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.get_n(timeout, amount, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('get_n', resource=resource, timeout=timeout, requested=amount, success=bool(retval), amount=retval)
        return retval

    def gget_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gget_n(timeout, amount, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('gget_n', resource=resource, timeout=timeout, requested=amount, success=bool(retval), amount=retval)
        return retval

    async def put(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.put(timeout, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('put', resource=resource, timeout=timeout, success=bool(retval), amount=retval)
        return retval

    def gput(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gput(timeout, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('gput', resource=resource, timeout=timeout, success=bool(retval), amount=retval)
        return retval

    async def put_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.put_n(timeout, amount, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('put_n', resource=resource, timeout=timeout, requested=amount, success=bool(retval), amount=retval)
        return retval

    def gput_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gput_n(timeout, amount, **policy_params)
        self.tx_changed.has_subscribers() and self._fire_changed('gput_n', resource=resource, timeout=timeout, requested=amount, success=bool(retval), amount=retval)
        return retval

    def put_nowait(self: Any, resource: DSResource) -> NumericType:
        retval = resource.put_nowait()
        self.tx_changed.has_subscribers() and self._fire_changed('put_nowait', resource=resource, success=bool(retval), amount=retval)
        return retval

    def put_n_nowait(self: Any, resource: DSResource, amount: NumericType = 1) -> NumericType:
        retval = resource.put_n_nowait(amount)
        self.tx_changed.has_subscribers() and self._fire_changed('put_n_nowait', resource=resource, requested=amount, success=bool(retval), amount=retval)
        return retval


class DSAgent(DSComponent, AgentProbeMixin, AgentContainerMixin, AgentResourceMixin):
    _dscomponent_instances: int = 0

    def __init__(self, *args: Any, name: Optional[str] = None, change_ep: Optional[DSPub] = None, **kwargs: Any) -> None:
        if name is None:
            name = type(self).__name__ + '.' + str(self._dscomponent_instances)
        super().__init__(name=name, *args, **kwargs)
        self.tx_changed = change_ep if change_ep is not None else self.sim.publisher(name=self.name + '.tx')
        self.state = 'created'
        kwargs.pop('name', None), kwargs.pop('sim', None)  # remove the two arguments
        process: DSProcess
        if inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = _ComponentProcess(self, self.process(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        elif inspect.ismethod(self.process):
            process = _ComponentProcess(self, DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        else:
            raise ValueError(f'The attribute {self.__class__}.process is not method, generator, neither coroutine.')
        self._scheduled_process: _ComponentProcess = process.schedule(0)
        self._instance_nr = self.__class__._dscomponent_instances + 1
        self.__class__._dscomponent_instances = self.instance_nr
        self._set_state('scheduled', reason='schedule')

    def _set_state(self, state: str, reason: str = '', **details: Any) -> bool:
        prev_state = self.state
        if prev_state == state:
            return False
        self.state = state
        self._fire_changed(reason=reason, change_type='state', prev_state=prev_state, **details)
        return True

    def _fire_changed(self, reason: str, change_type: str = 'action', prev_state: Optional[str] = None, **details: Any) -> None:
        if not self.tx_changed.has_subscribers():
            return
        if prev_state is None:
            prev_state = self.state
        event = {
            'kind': 'agent_state',
            'change_type': change_type,
            'agent': self,
            'state': self.state,
            'prev_state': prev_state,
            'reason': reason,
            'time': float(self.sim.time),
        }
        if details:
            event['details'] = details
        self.sim.signal(event, self.tx_changed)

    @property
    def instance_nr(self) -> int: return self._instance_nr
    
    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        pass

    def signal(self, event: EventType) -> None:
        self._scheduled_process.signal(event)

    def hold(self, timeout: TimeType = float('inf'), val: EventType = True) -> Generator[EventType, EventType, EventType]:
        '''Pause this agent for a duration (maps to gsleep).'''
        try:
            retval = yield from self.sim.gsleep(timeout=timeout, val=val)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('hold', timeout=timeout, event=retval)
        return retval

    def passivate(self, timeout: TimeType = float('inf'), val: EventType = True) -> Generator[EventType, EventType, EventType]:
        '''Wait until this agent receives any event (or timeout).'''
        try:
            retval = yield from self.sim.gwait(timeout=timeout, cond=AlwaysTrue, val=val)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('passivate', timeout=timeout, event=retval)
        return retval

    def activate(self, event: EventType = True) -> None:
        '''Activate this agent by sending an event to itself.'''
        self.tx_changed.has_subscribers() and self._fire_changed('activate', event=event)
        self.signal(event)

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue) -> EventType:
        try:
            retval = await self.sim.wait(timeout, cond=cond)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('wait', timeout=timeout, event=retval)
        return retval

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from self.sim.gwait(timeout, cond=cond)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        self.tx_changed.has_subscribers() and self._fire_changed('gwait', timeout=timeout, event=retval)
        return retval


class _ComponentProcess(DSProcess):
    def __init__(self, process_component: DSAgent, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._component = process_component

    @property
    def component(self) -> DSAgent:
        return self._component

    def _mark_started(self, add_timeout_cond: bool) -> None:
        super()._mark_started(add_timeout_cond)
        self._component._set_state('running', reason='process_start')

    def finish(self, value: EventType) -> EventType:
        retval = super().finish(value)
        self._component._set_state('finished', reason='process_finish', value=value)
        return retval

    def fail(self, exc: Exception) -> Exception:
        retval = super().fail(exc)
        self._component._set_state('failed', reason='process_fail', exc=repr(exc))
        return retval


class PCGenerator(DSAgent):
    def __init__(self, cls: Type[DSComponent], wait_method: Callable[[DSComponent], float] = lambda last: 1, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        self.cls = cls
        self.wait_method = wait_method
        if name is None:
            name = f'PCGenerator({cls.__name__ }).' + str(self._dscomponent_instances)
        super().__init__(*args, name=name, **kwargs)

    async def process(self) -> None:
        while True:
            obj = self.cls()  # create new instance of the class
            await self.sim.sleep(self.wait_method(obj))


# Backward-compatibility alias; DSAgent is the preferred name.
DSProcessComponent = DSAgent
      
