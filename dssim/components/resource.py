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
from dssim.simulation import DSComponent, DSSchedulable
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
            self.tx_changed.schedule(0, info='resource changed')
        return amount

    def put(self, timeout=float('inf'), amount=1):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        self.amount += amount
        self.tx_changed.schedule(0, info='resource changed')

    def get_nowait(self, amount=1):
        if amount > self.amount:
            retval = None
        else:
            self.amount -= amount
            self.tx_changed.schedule(0, info='resource changed')
        return amount

    def get(self, timeout=float('inf'), amount=1):
        ''' Get resource. If the resource has not enough amount, wait to have enough requested amount. '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_wait(timeout, cond=lambda e:self.amount >= amount)
        if retval is not None:
            self.amount -= amount
            self.tx_changed.schedule(0, info='resource changed')
        return retval
