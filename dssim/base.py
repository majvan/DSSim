# Copyright 2023- majvan (majvan@gmail.com)
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
The base classes / intefaces / mixin for dssim framework.
'''

class DSTrackableEvent:
    def __init__(self, value):
        self.value = value
        self.producers = []

    def track(self, producer):
        self.producers.append(producer)

    def __repr__(self):
        return f'DSTrackableEvent({self.value})'


def TrackEvent(fcn):
    def api(self, event, *args, **kwargs):
        if isinstance(event, DSTrackableEvent):
            event.producers.append(self)
        return fcn(self, event, *args, **kwargs)
    return api

class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, producer=None, **info):
        super().__init__()
        self.producer = producer
        self.info = info


class DSAbsTime:
    def __init__(self, value):
        self.value = value


class ICondition:
    def check(self): pass


class StackedCond(ICondition):
    def __init__(self):
        self.conds = []
        self.value = None

    def push(self, cond):
        self.conds.append(cond)
        return self

    def pop(self):
        return self.conds.pop()

    def check_one(self, cond, event):
        ''' Returns pair of info ("event passing", "value of event") '''
        # Check the event first
        # Instead of the following generic rule, it is better to add it as a stacked condition
        # for "None" value, it will be caught later by cond == event rule.
        # if event is None:  # timeout received
        #     return True, None
        if isinstance(event, Exception):  # any exception raised
            return True, event
        # Check the type of condition
        if cond == event:  # we are expecting exact event and it came
            return True, event
        elif isinstance(cond, ICondition):
            return cond.check(event)
        elif callable(cond) and cond(event):  # there was a filter function set and the condition is met
            return True, event
        else:  # the event does not match our condition and hence will be ignored
            return False, None
    
    def check(self, event):
        signaled, retval = None, event
        for cond in self.conds:
            signaled, event = self.check_one(cond, retval)
            if signaled:
                if hasattr(cond, 'cond_value'):
                    retval = cond.cond_value()
                else:
                    retval = event
                self.value = retval
                break
        return signaled, retval

    def cond_value(self):
        return self.value


class DSTransferableCondition(ICondition):
    def __init__(self, cond, transfer=lambda e:e):
        self.cond = StackedCond().push(cond)
        self.transfer = transfer
        self.value = None

    def check(self, value):
        signaled, retval = self.cond.check(value)
        if signaled:
            retval = self.transfer(retval)
        return signaled, retval


class SignalMixin:
    def signal(self, event):
        ''' Signal event. '''
        return self.sim.signal(self, event)

    def signal_kw(self, **event):
        ''' Signal key-value event type as kwargs. '''
        return self.sim.signal(self, event)

    def schedule_event(self, time, event):
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)

    def schedule_kw_event(self, time, **event):
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)


class DSComponentSingleton:
    sim_singleton = None


class DSComponent:
    ''' DSComponent is any component which uses simulation (sim) environment.
    The component shall have assigned a simulation instance (useful when
    creating more simulation instances in one application).
    If the sim instance is not specified, the one from singleton will be assigned.

    The interface has a rule that every instance shall have a (unique) name
    (useful for debugging when debugger displays interface name).
    If the name is not specified, it is created from the simulation instance
    and class name.
    '''
    def __init__(self, *args, name=None, sim=None, **kwargs):
        # It is recommended that core components specify the sim argument, i.e. sim should not be None
        self.sim = sim or DSComponentSingleton.sim_singleton
        if not isinstance(getattr(self.sim, 'names', None), dict):
            self.sim.names = {}
        temp_name = name or f'{self.__class__}'
        if self.sim is None:
            raise ValueError(f'Interface {temp_name} does not have sim parameter set and no DSSimulation was created yet.')
        if name is None:
            name = temp_name
            counter = self.sim.names.get(name, 0)
            self.sim.names[name] = counter + 1
            name = name + f'{counter}'
        elif name in self.sim.names:
            raise ValueError(f'Interface with name {name} already registered in the simulation instance {self.sim.name}.')
        else:
            self.sim.names[name] = 0
        self.name = name

    def __repr__(self):
        return self.name

