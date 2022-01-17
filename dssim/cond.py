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
This file implements advanced filtering logic - with overloading operators
to be able create advanced expressions.
'''
import inspect
from multiprocessing import parent_process
from dssim.simulation import DSProcess, sim
from dssim.pubsub import DSConsumer


class DSFilter:
    def __init__(self, cond=None, reevaluate=False, signal_timeout=False):
        self.signaled = False
        self.value = None
        self.cond = cond
        self.parent_process = sim.parent_process
        # Reevaluation means that after every event we receive we have to re-evaluate
        # the condition
        # If not reevaluation set, then once filter matches, it is swapped to signaled
        self.reevaluate = reevaluate
        # Signalling timeout is for generators. If a generator returns with None, this means
        # that it timed out. If signal_timeout is True, such timeout would be understood
        # as a valid signal.
        self.signal_timeout = signal_timeout
        if inspect.isgenerator(self.cond):
            # We create a new process from generator. This is required:
            # 1. (TODO: document!) Events scheduled only for the current process: they won't be taken by the new process 
            # 2. (TODO: implement!) Events which are taken by the current process from subscription will go to the
            #    new process because it has to inherit (fork) all the subscriptions from the current process
            # 3. Events which will be scheduled only for the new process (i.e. the new process schedules for himself)
            #    won't be taken by the current process
            # 4. The condition is computed on the return value of the new process
            # 5. Because of [3] and [4], we have to know the return value but because the process may run his own events,
            #    the processing could be asynchronous with execution of this filter; i.e. it could return asynchronously.
            #    For such, we subscribe for the new process finish event and push that to the current process
            if inspect.getgeneratorstate(self.cond) == inspect.GEN_CREATED:
                self.cond = sim.schedule(0, DSProcess(self.cond))  # convert to DSProcess so we could get return value
                self.subscriber = DSConsumer(self, self._process_finished)
                self.cond.finish_tx.add_subscriber('pre', self.subscriber)
                # sim._kick(self.cond)
            else:
                raise ValueError('Cannot filter already running generator.')

    def __or__(self, other):
        retval = DSFilterAggregated(any, self, other)
        return retval

    def __and__(self, other):
        retval = DSFilterAggregated(all, self, other)
        return retval

    def __str__(self):
        return f'DSFilter({self.cond})'

    def __eq__(self, event):
        retval = False
        if event is self:
            retval = True
        elif self.cond == event:
            retval = True
        return retval

    def __bool__(self):
        return self.signaled

    def __call__(self, other):
        if self.signaled and not self.reevaluate:
            return True
        if isinstance(self.cond, DSProcess):
            # now we should get this signaled only after return
            if self.cond.finished:
                if self.cond.value is None and self.signal_timeout:
                    self.value = None
                    self.signaled = True
                elif isinstance(self.cond.value, Exception):
                    pass
                else:
                    self.value = self.cond.value
                    self.signaled = True
        elif callable(self.cond) and self.cond(other):
            self.value = other
            self.signaled = True
        elif self == other:
            self.value = other
            self.signaled = True
        return self.signaled

    def _process_finished(self, *args, **kwargs):
        # Following forces re-evaluation by injecting new event
        self.cond.finish_tx.remove_subscriber(self.subscriber)
        sim.signal(self.parent_process, producer=self.cond, finished=True)


class DSFilterAggregated:
    def __init__(self, expression, *elements):
        self.expression = expression
        self.elements = list(elements)

    def __or__(self, other):
        if self.expression is any:
            self.elements.append(other)
            return self
        else:
            return DSFilterAggregated(any, self, other)

    def __and__(self, other):
        if self.expression is all:
            self.elements.append(other)
            return self
        else:
            return DSFilterAggregated(all, self, other)

    def __bool__(self):
        return self.expression(self.elements)

    def __str__(self):
        strings = [str(v) for v in self.elements]
        expression = '|' if self.expression == any else '&'
        return '(' + f' {expression} '.join(strings) + ')'

    def __call__(self, event):
        ''' Handles logic for the event. '''
        # This converts from callable object into method calling.
        for el in self.elements:
            el(event)
        retval = self.expression(self.elements)
        if retval:
            # TODO: instead of boolean (True), return dict with signalled objects
            pass
        return retval
