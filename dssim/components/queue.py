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
from dssim.simulation import DSComponent, DSSchedulable
from dssim.pubsub import DSProducer


class Queue(DSComponent):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity=float('inf'), *args, **kwargs):
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.tx_queue_changed = DSProducer(name=self.name+'.tx')
        self.capacity = capacity
        self.queue = []

    def _enqueue(self, obj):
        self.queue.append(obj)
        return obj

    def _dequeue(self):
        return self.queue.pop(0)

    def append(self, obj):
        self.queue.append(obj)
        self.tx_queue_changed.schedule(0, info='queue changed')
        return obj

    def pop(self, index):
        retval = None
        if len(self.queue) > index:
            retval = self.queue.pop(index)
            self.tx_queue_changed.schedule(0, info='queue changed')
        return retval

    def put_nowait(self, **obj):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        if len(self) < self.capacity:
            retval = self.append(obj)  # will emit "queue changed"
        else:
            retval = None
        return retval

    def put(self, timeout=float('inf'), **obj):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_queue_changed):
            retval = yield from self.sim.check_and_wait(timeout, cond=lambda e:len(self) < self.capacity)  # wait while first element does not match the cond
        if retval is not None:
            self.append(obj)  # will emit "queue changed"
        return retval

    def get_nowait(self, cond=lambda c: True):
        if len(self) > 0 and cond(self[0]):
            retval = self.pop(0)  # will emit "queue changed"
        else:
            retval = None
        return retval

    def get(self, timeout=float('inf'), cond=lambda c: True):
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        with self.sim.consume(self.tx_queue_changed):
            retval = yield from self.sim.check_and_wait(timeout, cond=lambda e:len(self) > 0 and cond(self.queue[0]))  # wait while first element does not match the cond
        if retval is not None:
            retval = self.pop(0)  # will emit "queue changed"
        return retval

    def remove(self, cond):
        ''' Removes event(s) from queue '''
        # Get list of elements to be removed
        if len(self.queue) > 0:
            # Remove all others except the first one
            self.queue = [e for e in self.queue if not ((callable(cond) and cond(e) or (cond == e)))]
            # now find what we may emit: "queue changed"

    def __len__(self):
        return len(self.queue)

    def __getitem__(self, index):
        return self.queue[index]

    def __iter__(self):
        return iter(self.queue)


