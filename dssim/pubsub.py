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
from dssim.simulation import DSInterface

class DSAbstractConsumer(DSInterface):
    ''' An interface for a consumer '''

    @abstractmethod
    def notify(self, **data):
        ''' This method is called to notify about an event. '''
        raise NotImplementedError('Abstract method, use derived classes')

class DSConsumer(DSAbstractConsumer):
    ''' A consumer interface.
    The only functionality a consumer interface provides is to
    forward the signal (event) to other (non-DSInterface) interfaces.
    '''
    def __init__(self, forward_method, cond=lambda e: True, **kwargs):
        super().__init__(**kwargs)
        self.forward_method = forward_method
        self.cond = cond

    def notify(self, **data):
        ''' The function calls all the registered methods from objects after passing filter. '''
        retval = False
        if callable(self.cond) and self.cond(data) or self.cond == data:
            retval = self.forward_method(**data)
        return retval
        

class DSAbstractProducer(DSInterface):
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


class DSProducer(DSAbstractProducer):
    ''' Full feature producer which can signal events to the attached consumers. '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # queue [notify_in_progress?] [phase] [process or function?]
        self.subs = {
            'pre': {
                False: {},
                True: {},
            },
            'act': {
                False: {},
                True: {},
            },
            'post': {
                False: {},
                True: {},
            },
        }

    def add_subscriber(self, subscriber, phase='act'):
        if subscriber:
            subs = self.subs[phase][isinstance(subscriber, Iterable)]
            subs[subscriber] = subs.get(subscriber, 0) + 1

    def remove_subscriber(self, subscriber, phase='act'):
        if subscriber:
            subs = self.subs[phase][isinstance(subscriber, Iterable)]
            subs[subscriber] = subs.get(subscriber, 0) - 1

    def signal(self, **event_data):
        ''' Send signal object to the subscribers '''

        # Emit the signal to all pre-observers
        for subscriber, refs in self.subs['pre'][False].items():
            subscriber.notify(**event_data) if refs else None
        for subscriber, refs in self.subs['pre'][True].items():
            self.sim.signal(subscriber, **event_data) if refs else None

        # Emit the signal to all consumers and stop with the first one
        # which accepted the signal
        for subscriber, refs in self.subs['act'][False].items():
            if refs and subscriber.notify(**event_data):
                break
        else:
            for subscriber, refs in self.subs['act'][True].items():
                if refs and self.sim.signal(subscriber, **event_data):
                    break
            else:
                # Emit the signal to all post-observers
                for subscriber, refs in self.subs['post'][False].items():
                    subscriber.notify(**event_data) if refs else None
                for subscriber, refs in self.subs['post'][True].items():
                    self.sim.signal(subscriber, **event_data) if refs else None

        # cleanup- remove items with zero references
        # We do not cleanup in remove_subscriber, because remove_subscriber could
        # be called from the notify(...) and that could produce an error 
        for phase in self.subs:
            for process_or_fcn in self.subs[phase]:
                old_dict = self.subs[phase][process_or_fcn]
                new_dict = {k: v for k, v in old_dict.items() if v > 0}
                self.subs[phase][process_or_fcn] = new_dict
