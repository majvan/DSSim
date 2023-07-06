# Copyright 2021-2022 NXP Semiconductors
# Copyright 2021- majvan (majvan@gmail.com)
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
A resource is an object representing a pool of abstract resources with amount filled in.
Compared to queue, resource works with non-integer amounts but it does not contain object
in the pool, just an abstract pool level information (e.g. amount of water in a tank).
'''
from typing import Any, Generator, TYPE_CHECKING
from dssim.base import NumericType, TimeType, EventType
from dssim.components.base import DSStatefulComponent, DSProbedComponent


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Resource(DSStatefulComponent, DSProbedComponent):
    ''' The Resource models a container of virtual resource(s).
    By virtual, it means that the components holds only the amount of the resources,
    not individual objects. The amount can be divisable to any extent, it is represented
    by float type.
    '''
    def __init__(self, amount: NumericType = 0, capacity: NumericType = float('inf'), *args: Any, **kwargs: Any) -> None:
        ''' Init Resource component.
        Capacity is max. capacity the resource can handle.
        Amount is initial amount of the resources.
        '''
        super().__init__(*args, **kwargs)
        if amount > capacity:
            raise ValueError('Initial amount of the resource is greater than capacity.')
        self.amount = amount
        self.capacity = capacity

    def _set_loggers(self):
        super()._set_loggers()
        self.put_logger = []
        self.get_logger = []

    def _set_probed_methods(self):
        super()._set_probed_methods()
        self.put = self.probed_coroutine(self._put, self.put_logger)
        self.gput = self.probed_generator(self._gput, self.put_logger)
        self.get = self.probed_coroutine(self._get, self.get_logger)
        self.gget = self.probed_generator(self._gget, self.get_logger)
    
    def _set_unprobed_methods(self):
        super()._set_unprobed_methods()
        self.put = self._put
        self.gput = self._gput
        self.get = self._get
        self.gget = self._gget

    def put_nowait(self, amount: NumericType) -> NumericType:
        if self.amount + amount > self.capacity:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval

    async def _put(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Put amount into the resource pool.  '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval

    def _gput(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put amount into the resource pool.  '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval

    def get_nowait(self, amount: NumericType = 1):
        if amount > self.amount:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval

    async def _get(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Get resource. If the resource has not enough amount, wait to have enough requested amount. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval

    def _gget(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get resource. If the resource has not enough amount, wait to have enough requested amount. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.tx_changed.schedule_event(0, {'event': 'resource changed', 'process': self.sim.pid})
            retval = amount
        return retval


class Mutex(Resource):
    def __init__(self, *args, **kwargs):
        super().__init__(1, 1, *args, **kwargs)
        self.last_owner = None
        self.context_manager_timeout = None
        self.policy_params = kwargs

    async def lock(self, timeout=float('inf'), **policy_params: Any):
        retval = await self.get(timeout, **policy_params)
        if retval is not None:
            # store the info that the mutext is owned by us
            self.last_owner = self.sim.pid
        return retval
    
    def open(self, timeout=float('inf')):
        self.context_manager_timeout = timeout
        return self

    def locked(self):
        return self.amount == 0

    def release(self):
        if self.amount == 0:
            return self.put_nowait(1)

    async def __aenter__(self):
        if self.context_manager_timeout is None:
            raise ValueError(f'You try to use context manager "async with {self}" but you need to use open() function for that.')
        event = await self.lock(self.context_manager_timeout, **self.policy_params)
        self.context_manager_timeout = None
        return event

    def __enter__(self):
        # Unfortunately, it is not possible to yield here. So the caller has to yield from lock() after with
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.pid:
            self.release()

    def __exit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.pid:
            self.release()


# In the following, self is in fact of type DSProcessComponent, but PyLance makes troubles with variable types
class ResourceMixin:
    async def get(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.get(timeout, amount, **policy_params)
        return retval
            
    def gget(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gget(timeout, amount, **policy_params)
        return retval
            
    async def put(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        retval = await resource.put(timeout, amount, **policy_params)
        return retval

    def gput(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        retval = yield from resource.gput(timeout, amount, **policy_params)
        return retval
    
    def put_nowait(self: Any, resource: Resource, amount: NumericType = 1) -> NumericType:
        retval = resource.put_nowait(amount)
        return retval



# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimResourceMixin:
    def resource(self: Any, *args: Any, **kwargs: Any) -> Resource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in resource() method should be set to the same simulation instance.')
        return Resource(*args, **kwargs, sim=sim)
