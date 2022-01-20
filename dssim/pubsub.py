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
This file defines producers (publishers) and consumers (subscribers)
'''
from abc import abstractmethod
from inspect import isgeneratorfunction
from dssim.simulation import DSInterface, DSProcess

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
    def __init__(self, forward_obj, forward_method, cond=lambda e: True, **kwargs):
        super().__init__(**kwargs)
        self.forward_obj = forward_obj
        self.forward_method = forward_method
        self.cond = cond

    def notify(self, **data):
        ''' The function calls all the registered methods from objects after passing filter. '''
        if self.cond(data):
            self.forward_method(self.forward_obj, **data)

class DSProcessConsumer(DSAbstractConsumer, DSProcess):
    ''' A consumer which can consume events in a schedulable process.
    '''
    def __init__(self, process, start=False, delay=0, **kwargs):
        DSProcess.__init__(self, generator=process, **kwargs)
        assert self.generator == process
        if start:
            process = self.schedule(delay) # update the process with parent decorator
        elif delay != 0:
            raise ValueError('The process can be delayed only if started at initialization')

    def notify(self, **data):
        ''' Interface which can pass event into a waiting process.
        Note that a notification to a not yet started process will start it
        '''
        self.sim.signal(self, **data)

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
        if consumer_process:
            self.sim.schedule_event(time_delta, event_data, consumer_process)
        else:
            dsevent = self.encapsulate_data_to_transport(**event_data)
            self.sim.schedule_event(time_delta, dsevent, self.sim.time_process)

    @abstractmethod
    def add_consumer(self, consumer):
        ''' Add a consumer to the list of consumers connected to this producer '''
        raise NotImplementedError('Abstract method, use derived classes')

    @abstractmethod
    def get_consumers(self):
        ''' Get the list of consumers associated with this producer '''
        raise NotImplementedError('Abstract method, use derived classes')

    @abstractmethod
    def signal(self, **event_data):
        ''' Emit signal to associated consumers '''
        raise NotImplementedError('Abstract method, use derived classes')


class DSProducer(DSAbstractProducer):
    ''' Full feature producer which can signal events to the attached consumers. '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.consumers = []
        self.process_consumers = []
        self._single_process_consumer = False

    def add_consumer(self, consumer):
        if isinstance(consumer, DSProcess):
            self.process_consumers.append(consumer)
        else:
            self.consumers.append(consumer)

    def get_consumers(self):
        return self.consumers + self.process_consumers

    def signal(self, **event_data):
        ''' Emit a signal to be received by all consumers.'''
        for consumer in self.consumers:
            # To increase performance, we just call the consumer directly.
            # The correct decoupled code would be self.sim.signal(c, **event_data)
            consumer.notify(**event_data)
        for consumer in self.process_consumers:
            consumer.notify(**event_data)

    def schedule(self, time_delta, **event_data):
        ''' Schedule future event with parametrized event '''
        for consumer in self.process_consumers:
            # To reduce cycles, for the DSProcessConsumer we could already schedule against
            # their process.
            # 1. Producer -> schedule_event(event, time_process) (and returns)
            # 2. Simulator -> signal_object(time_process, encapsulated_event)
            # 3.   signal_object -> send(time_process, encapsulated_event)
            # 4.     time_process -> get the encapsulated producer
            # and in the case of the only DSProcessConsumer attached, following would happen:
            # 5.         Producer -> notify(DSProcessConsumer, event)
            # 6.           DSProcessConsumer -> signal(event) = send(process, event)
            # With this shortcut, we change the this flow to:
            # 1. Producer -> schedule_event(event, time_process) (and returns)
            # 2. Simulator -> signal_object(process, event)
            # 3.   signal_object -> send(time_process, event)
            # That means performance improvement.
            # The drawback of this solution is that the number of consumers is evaluated
            # in the time of scheduling the event, not in the time when event occurs. This
            # is typically not an issue.
            super().schedule(time_delta, consumer, **event_data)
        if self.consumers:
            # Before scheduling of the event, check if it will be consumed.
            # If not- useless schedule => ignore
            super().schedule(time_delta, **event_data)

class DSSingleProducer(DSProducer):
    ''' A producer which has only single consumer is removed for simplicity.
    The more generic DSProducer logic is used instead.
    '''
