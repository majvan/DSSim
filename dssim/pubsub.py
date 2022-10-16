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
from collections.abc import Iterable
from abc import abstractmethod
from dssim.simulation import DSComponent


class DSAbstractProducer(DSComponent):
    ''' Provides base abstract class for producers '''

    def encapsulate_data_to_transport(self, **event_data):
        ''' Encapsulates data to an object suitable for transport layer.

        We use simple dict for transport object.

        At the beginning we allow caller to define (fake) the provider.
        That could be a little useful to better debugging (of digital system), i.e.
        when a event is notified from an internal producer, we can make it
        to look as it was called from the official TX.
        '''
        producer = event_data.get('producer', self)
        event_data['producer'] = producer
        return event_data

    def schedule(self, time_delta, consumer_process=None, **event_data):
        ''' Schedule future event with parametrized event '''

        # We will schedule all the future events into time_process and not directly
        # to the attached subscribers. The reason is simple- in the time of the event
        # evaluation (in the future) the set of attached subscribers can be different.

        # Another reason is that signalling directly from a component can create
        # cyclic signalling dependency (an event from processA signals processB, it
        # executes immediately and tries to send signal to processA). Decoupling with
        # schedule could be a solution.

        # The last caveat of signalling is the order of execution. For instance, if
        # processA gets signal i.e. "char A available on serial line", executes and
        # frees serial line which in turn triggers signal i.e. "char B available
        # on serial line" which now triggers processB, then the processB executes
        # and preempts processA to finish its "char A" execution first.
        # Though both events happen in the same sim.time, the execution is typically
        # expected to run sequentially.

        dsevent = self.encapsulate_data_to_transport(**event_data)
        self.sim.schedule_event(time_delta, dsevent, self.sim.time_process)

    @abstractmethod
    def add_subscriber(self, subscriber, phase):
        ''' Add a subscriber to the list of subscribers connected to this producer '''
        raise NotImplementedError('Abstract method, use derived classes')

    @abstractmethod
    def remove_subscriber(self, subscriber, phase):
        ''' Remove subscriber from the list of subscribers connected to this producer '''
        raise NotImplementedError('Abstract method, use derived classes')

    @abstractmethod
    def signal(self, **event_data):
        ''' Emit signal to associated subscribers '''
        raise NotImplementedError('Abstract method, use derived classes')


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
        priority_dict[key] = priority_dict.get(key, 0) + 1

    def cleanup(self):
        new_prio_dict = {}
        for key, old_dict in self.d.items():
            new_dict = {k: v for k, v in old_dict.items() if v > 0}
            if new_dict:
                new_prio_dict[key] = new_dict
        self.d = new_prio_dict


class DSProducer(DSAbstractProducer):
    ''' Full feature producer which can signal events to the attached consumers. '''
    def __init__(self, notifier=NotifierDict, **kwargs):
        super().__init__(**kwargs)
        self.subs = {
            'pre': notifier(),
            'act': notifier(),
            'post': notifier(),
        }

    def add_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.inc(subscriber, **kwargs)

    def remove_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.dec(subscriber, **kwargs)

    def wait(self, timeout=float('inf'), cond=lambda e:True, val=True):
        with self.sim.consume(self):
            retval = yield from self.sim.wait(timeout, cond=cond, val=val)
        return retval

    def signal(self, **event_data):
        ''' Send signal object to the subscribers '''

        # Emit the signal to all pre-observers
        for subscriber, refs in self.subs['pre']:
            self.sim.signal(subscriber, **event_data) if refs else None

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        for subscriber, refs in self.subs['act']:
            if refs and self.sim.signal(subscriber, **event_data):
                self.subs['act'].rewind()  # this will rewind for round robin
                break
        else:
            # Emit the signal to all post-observers
            for subscriber, refs in self.subs['post']:
                self.sim.signal(subscriber, **event_data) if refs else None

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error 
        for queue in self.subs.values():
            queue.cleanup()
