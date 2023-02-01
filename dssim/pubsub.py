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
from dssim.simulation import DSComponent, IConsumer

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


class _ProducerMetadata():
    def __init__(self):
        # The producer is signaled when a deferred event from the same producer appears.
        # In such case the simulator checks for the condition and if met, it calls the producer's send method.
        # Thus, the condition is always meet. Another conditions are checked when calling callbacks
        self.cond = lambda e: True


class DSProducer(DSComponent, IConsumer):
    ''' Full feature producer which consume signal events and resends it to the attached consumers. '''
    def __init__(self, notifier=NotifierDict, **kwargs):
        super().__init__(**kwargs)
        self.subs = {
            'pre': notifier(),
            'act': notifier(),
            'post': notifier(),
        }
        self.create_metadata()

    def create_metadata(self):
        return _ProducerMetadata()

    def add_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.inc(subscriber, **kwargs)

    def remove_subscriber(self, subscriber, phase='act', **kwargs):
        if subscriber:
            subs = self.subs[phase]
            subs.dec(subscriber, **kwargs)

    def send(self, event):
        ''' Send signal object to the subscribers '''

        # Emit the signal to all pre-observers
        for subscriber, refs in self.subs['pre']:
            self.sim.send(subscriber, event) if refs else None

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        for subscriber, refs in self.subs['act']:
            if refs and self.sim.send(subscriber, event):
                self.subs['act'].rewind()  # this will rewind for round robin
                break
        else:
            # Emit the signal to all post-observers
            for subscriber, refs in self.subs['post']:
                self.sim.send(subscriber, event) if refs else None

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error 
        for queue in self.subs.values():
            queue.cleanup()

    def signal(self, event):
        ''' Send an event to the producer. The event will be processed by simulator
        instance and then sent back to us by the send() method '''
        self.sim.signal(self, event)

    def signal_kw(self, **event):
        ''' Signal a key-value event as dict '''
        self.signal(event)

    def schedule_event(self, time, event):
        # We will schedule all the future events into our producer and not to the
        # attached subscribers. The reason is simple- in the time of the event
        # evaluation (in the future) the set of attached subscribers can be different.

        # Another usage of this method is with zero time_delta. In that case it can
        # defer the direct consumer calls back to the simulation and preventing thus
        # cyclic signalling dependency (an event from processA sends directly to
        # processB, it executes immediately and tries to send signal to processA).
        # Decoupling with zero time schedule could be a solution.

        # The last caveat of signalling is the order of execution. For instance, if
        # processA gets signal i.e. "char A available on serial line", executes and
        # frees serial line which in turn triggers signal i.e. "char B available
        # on serial line" which now triggers processB, then the processB executes
        # and preempts processA to finish its "char A" execution first.
        # Though both events happen in the same sim.time, the execution process is
        # typically expected to run sequentially.
        return self.sim.schedule_event(time, event, self)

    def schedule_kw_event(self, time, **event):
        return self.sim.schedule_event(time, event, self)
        
    def wait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        with self.sim.consume(self):
            retval = yield from self.sim.wait(timeout, cond, val)
        return retval
