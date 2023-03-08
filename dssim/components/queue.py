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
A queue of events with runtime flexibility of put / get events.
'''
from dssim.simulation import DSComponent, IConsumer
from dssim.pubsub import DSProducer


class Queue(DSComponent, IConsumer):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity=float('inf'), *args, **kwargs):
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.tx_changed = DSProducer(name=self.name+'.tx', sim=self.sim)
        self.capacity = capacity
        self.queue = []

    def send(self, event):
        return self.put_nowait(event) is not None

    def signal(self, event):
        return self.sim.signal(self, event)
    
    def signal_kw(self, **event):
        return self.sim.signal(self, event)

    def schedule_event(self, time, event):
        return self.sim.schedule_event(time, event, self)

    def schedule_kw_event(self, time, **event):
        return self.sim.schedule_event(time, event, self)

    def put_nowait(self, *obj):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        if len(self) + len(obj) <= self.capacity:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
            retval = obj
        else:
            retval = None
        return retval

    async def put(self, timeout=float('inf'), *obj):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e:len(self) + len(obj) <= self.capacity)  # wait while first element does not match the cond
        if retval is not None:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def gput(self, timeout=float('inf'), *obj):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_gwait(timeout, cond=lambda e:len(self) + len(obj) <= self.capacity)  # wait while first element does not match the cond
        if retval is not None:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def get_nowait(self, amount=1, cond=lambda e: True):
        if len(self) >= amount and cond(self.queue[:amount]):
            retval = self.queue[:amount]
            self.queue = self.queue[amount + 1:]
            self.tx_changed.schedule_event(0, 'queue changed')
        else:
            retval = None
        return retval

    async def get(self, timeout=float('inf'), amount=1, cond=lambda e: True):
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e:len(self) >= amount and cond(self.queue[0]))  # wait while first element does not match the cond
        if retval is not None:
            retval = self.queue[:amount]
            self.queue = self.queue[amount:]
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def gget(self, timeout=float('inf'), amount=1, cond=lambda e: True):
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_gwait(timeout, cond=lambda e:len(self) >= amount and cond(self.queue[0]))  # wait while first element does not match the cond
        if retval is not None:
            retval = self.queue[:amount]
            self.queue = self.queue[amount:]
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def pop(self, index=0, default=None):
        retval = None
        if len(self.queue) > index:
            try:
                retval = self.queue.pop(index)
                self.tx_changed.schedule_event(0, 'queue changed')
            except IndexError as e:
                retval = default
        return retval

    def remove(self, cond):
        ''' Removes event(s) from queue '''
        # Get list of elements to be removed
        length = len(self.queue)
        if length > 0:
            # Remove all others except the first one
            self.queue = [e for e in self.queue if not ((callable(cond) and cond(e) or (cond == e)))]
            # now find what we may emit: "queue changed"
            if length != len(self.queue):
                self.tx_changed.schedule_event(0, 'queue changed')

    def __len__(self):
        return len(self.queue)

    def __getitem__(self, index):
        return self.queue[index]

    def __setitem__(self, index, data):
        self.queue[index] = data
        self.tx_changed.schedule_event(0, 'queue changed')

    def __iter__(self):
        return iter(self.queue)
