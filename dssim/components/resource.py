# Copyright 2021 NXP Semiconductors
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
from dssim.simulation import DSComponent, Awaitable
from dssim.pubsub import DSProducer


class Resource(DSComponent):
    ''' The Resource models a container of virtual resource(s).
    By virtual, it means that the components holds only the amount of the resources,
    not individual objects. The amount can be divisable to any extent, it is represented
    by float type.
    '''
    def __init__(self, amount=0, capacity=float('inf'), *args, **kwargs):
        ''' Init Resource component.
        Capacity is max. capacity the resource can handle.
        Amount is initial amount of the resources.
        '''
        super().__init__(*args, **kwargs)
        if amount > capacity:
            raise ValueError('Initial amount of the resource is greater than capacity.')
        self.tx_changed = DSProducer(name=self.name+'.tx', sim=self.sim)
        self.amount = amount
        self.capacity = capacity

    def put_nowait(self, amount):
        if self.amount + amount > self.capacity:
            retval = None
        else:
            self.amount += amount
            self.tx_changed.schedule_event(0, 'resource changed')
        return amount

    async def put(self, timeout=float('inf'), amount=1):
        ''' Put amount into the resource pool.  '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        self.amount += amount
        self.tx_changed.schedule_event(0, 'resource changed')

    def get_nowait(self, amount=1):
        if amount > self.amount:
            retval = None
        else:
            self.amount -= amount
            self.tx_changed.schedule_event(0, 'resource changed')
        return amount

    async def get(self, timeout=float('inf'), amount=1):
        ''' Get resource. If the resource has not enough amount, wait to have enough requested amount. '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount >= amount)
        if retval is not None:
            self.amount -= amount
            self.tx_changed.schedule_event(0, 'resource changed')
        return retval


class Mutex(Resource):
    def __init__(self, *args, **kwargs):
        super().__init__(1, 1, args, **kwargs)
        self.last_owner = None
        self.context_manager_timeout = None

    async def lock(self, timeout=float('inf')):
        retval = await self.get(timeout)
        if retval is not None:
            # store the info that the mutext is owned by us
            self.last_owner = self.sim.parent_process
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
        event = await self.lock(self.context_manager_timeout)
        self.context_manager_timeout = None
        return event

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.parent_process:
            self.release()

    def __enter__(self):
        # Unfortunately, it is not possible to yield here. So the caller has to yield from lock() after with
        return self

    def __aexit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.parent_process:
            self.release()
        return Awaitable()
