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
from dssim.components.base import DSStatefulComponent


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Resource(DSStatefulComponent):
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

    def put_nowait(self) -> NumericType:
        ''' Put 1 unit into the resource pool immediately. '''
        return self.put_n_nowait(1)

    def put_n_nowait(self, amount: NumericType) -> NumericType:
        ''' Put amount units into the resource pool immediately. '''
        if self.amount + amount > self.capacity:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
            retval = amount
        return retval

    async def put(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Put 1 unit into the resource pool, waiting if at capacity. '''
        return await self.put_n(timeout, 1, **policy_params)

    async def put_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Put amount units into the resource pool, waiting if at capacity. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
            retval = amount
        return retval

    def gput(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put 1 unit into the resource pool (generator version), waiting if at capacity. '''
        return (yield from self.gput_n(timeout, 1, **policy_params))

    def gput_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put amount units into the resource pool (generator version), waiting if at capacity. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
            retval = amount
        return retval

    def get_nowait(self) -> NumericType:
        ''' Get 1 unit from the resource pool immediately. '''
        return self.get_n_nowait(1)

    def get_n_nowait(self, amount: NumericType = 1) -> NumericType:
        ''' Get amount units from the resource pool immediately. '''
        if amount > self.amount:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
            retval = amount
        return retval

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Get 1 unit from the resource pool, waiting if not available. '''
        return await self.get_n(timeout, 1, **policy_params)

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Get amount units from the resource pool, waiting if not available. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
            retval = amount
        return retval

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get 1 unit from the resource pool (generator version), waiting if not available. '''
        return (yield from self.gget_n(timeout, 1, **policy_params))

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get amount units from the resource pool (generator version), waiting if not available. '''
        with self.sim.consume(self.tx_changed, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)
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
            return self.put_nowait()

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
    async def get(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get(timeout, **policy_params)

    def gget(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget(timeout, **policy_params))

    async def get_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get_n(timeout, amount, **policy_params)

    def gget_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget_n(timeout, amount, **policy_params))

    async def put(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put(timeout, **policy_params)

    def gput(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput(timeout, **policy_params))

    async def put_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put_n(timeout, amount, **policy_params)

    def gput_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput_n(timeout, amount, **policy_params))

    def put_nowait(self: Any, resource: Resource) -> NumericType:
        return resource.put_nowait()

    def put_n_nowait(self: Any, resource: Resource, amount: NumericType = 1) -> NumericType:
        return resource.put_n_nowait(amount)



# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimResourceMixin:
    def resource(self: Any, *args: Any, **kwargs: Any) -> Resource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in resource() method should be set to the same simulation instance.')
        return Resource(*args, **kwargs, sim=sim)
