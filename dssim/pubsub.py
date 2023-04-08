# Copyright 2020 NXP Semiconductors
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
from dssim.simulation import DSConsumer, SignalMixin, TrackEvent

class NotifierDict():
    def __init__(self):
        self.d = {}

    def __iter__(self):
        return iter(self.d.items())

    def rewind(self, *args, **kwargs):
        return

    def inc(self, key, **kwargs):
        self.d[key] = self.d.get(key, 0) + 1

    def dec(self, key, **kwargs):
        self.d[key] = self.d.get(key, 0) - 1

    def cleanup(self):
        old_dict = self.d
        new_dict = {k: v for k, v in old_dict.items() if v > 0}
        self.d = new_dict


class NotifierRoundRobin():
    def __init__(self):
        self.queue = []

    def __iter__(self):
        self.current_index = 0
        return self

    def __next__(self):
        if self.current_index >= len(self.queue):
            raise StopIteration
        retval = self.queue[self.current_index]
        self.current_index += 1
        return retval

    def rewind(self, *args, **kwargs):
        self.queue = self.queue[self.current_index:] + self.queue[:self.current_index:]

    def inc(self, key, **kwargs):
        for item in self.queue:
            if item[0] == key:
                item[1] += 1
                return
        self.queue.append([key, 1])

    def dec(self, key, **kwargs):
        for item in self.queue:
            if item[0] == key:
                item[1] -= 1
                return
        raise ValueError('A key was supposed to be in the queue')

    def cleanup(self):
        new_queue = []
        for item in self.queue:
            if item[1] > 0:
                new_queue.append(item)
        self.queue = new_queue


class NotifierPriority():
    def __init__(self):
        self.d = {}

    def __iter__(self):
        return iter(self.iterate_by_priority())

    def iterate_by_priority(self):
        for prio in sorted(self.d.keys()):
            for d in self.d[prio].items():
                yield d

    def rewind(self, *args, **kwargs):
        return

    def inc(self, key, priority, **kwargs):
        priority_dict = self.d[priority] = self.d.get(priority, {})
        priority_dict[key] = priority_dict.get(key, 0) + 1

    def dec(self, key, priority, **kwargs):
        priority_dict = self.d[priority] = self.d.get(priority, {})
        priority_dict[key] = priority_dict.get(key, 0) - 1

    def cleanup(self):
        new_prio_dict = {}
        for key, old_dict in self.d.items():
            new_dict = {k: v for k, v in old_dict.items() if v > 0}
            if new_dict:
                new_prio_dict[key] = new_dict
        self.d = new_prio_dict


class DSProducer(DSConsumer, SignalMixin):
    ''' Full feature producer which consume signal events and resends it to the attached consumers. '''
    def __init__(self, notifier=NotifierDict, **kwargs):
        super().__init__(**kwargs)
        self.subs = {
            'pre': notifier(),
            'act': notifier(),
            'post': notifier(),
        }
        # A producer takes any event - no conditional
        self.meta.cond.push(lambda e: True)

    def add_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.inc(subscriber, **kwargs)

    def remove_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.dec(subscriber, **kwargs)

    @TrackEvent
    def send(self, event):
        ''' Send signal object to the subscribers '''

        # Emit the signal to all pre-observers
        for subscriber, refs in self.subs['pre']:
            self.sim.send_with_cond(subscriber, event) if refs else None

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        for subscriber, refs in self.subs['act']:
            if refs and self.sim.send_with_cond(subscriber, event):
                self.subs['act'].rewind()  # this will rewind for round robin
                break
        else:
            # Emit the signal to all post-observers
            for subscriber, refs in self.subs['post']:
                self.sim.send_with_cond(subscriber, event) if refs else None

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error 
        for queue in self.subs.values():
            queue.cleanup()

    def gwait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        with self.sim.consume(self):
            retval = yield from self.sim.gwait(timeout, cond, val)
        return retval

    async def wait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        with self.sim.consume(self):
            retval = await self.sim.wait(timeout, cond, val)
        return retval

class DSTransformation(DSProducer):
    ''' A producer which takes a signal, transforms / wraps it to another signal and
    sends to a consumer.
    The typical use case is to transform events from one endpoint to a process as exceptions.
    '''
    def __init__(self, ep, transformation, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ep = ep
        self.transformation = transformation

    def add_subscriber(self, subscriber, *args, **kwargs):
        self.ep.add_subscriber(self, *args, **kwargs)
        retval = super().add_subscriber(subscriber, *args, **kwargs)
        return retval
    
    def remove_subscriber(self, subscriber, *args, **kwargs):
        self.ep.remove_subscriber(self, *args, **kwargs)
        retval = super().remove_subscriber(subscriber, *args, **kwargs)
        return retval

    @TrackEvent
    def send(self, event):
        event = self.transformation(event)
        retval = super().send(event)
        return retval
