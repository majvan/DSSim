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
from dssim.simulation import DSProcess, DSCondition, sim
from dssim.pubsub import DSConsumer


class DSFilter(DSCondition):
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
            # 1. (TODO: document!) Events scheduled only for the current process: they won't be taken by the new
            #    process.
            # 2. Events which are processed by the current process have go to the new process so it has to inherit
            #    (fork) all the subscriptions from the current process.
            #    Another possibility to solve this is to push all the events from this process to the new process.
            # 3. Events which will be scheduled only for the new process (i.e. the new process schedules for himself)
            #    won't be taken by the current process (of course).
            # 4. The condition is computed on the event object, which is return value of the process
            #    (retval None means timeout).
            # 5. Because of [3] and [4], we have to know the return value but because the process may be handling his
            #    own events, the processing could be asynchronous with execution of this filter; i.e. it could return
            #    asynchronously. For such, we subscribe for the new process finish event and push that to the current
            #    process.
            if inspect.getgeneratorstate(self.cond) == inspect.GEN_CREATED:
                self.cond = sim.schedule(0, DSProcess(self.cond))  # convert to DSProcess so we could get return value
                self.subscriber = DSConsumer(self, self._process_finished)
                self.cond.finish_tx.add_subscriber(self.subscriber, 'pre')
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

    def __bool__(self):
        return self.signaled

    def __call__(self, other):
        if self.signaled and not self.reevaluate:
            return True
        signaled, value = False, None
        if isinstance(self.cond, DSProcess):
            # now we should get this signaled only after return
            if self.cond.finished:
                if self.cond.value is None and self.signal_timeout:
                    signaled, value = True, None
                elif isinstance(self.cond.value, Exception):
                    pass
                else:
                    signaled, value = True, self.cond.value
            else:
                sim.signal(self.cond, **other)
        elif callable(self.cond) and self.cond(other):
            signaled, value = True, other
        elif self is other:
            signaled, value = True, other
        elif self.cond == other:
            signaled, value = True, other
        self.signaled, self.value = signaled, value
        return self.signaled

    def _process_finished(self, *args, **kwargs):
        # Following forces re-evaluation by injecting new event
        self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
        sim.signal(self.parent_process, producer=self.cond, finished=True)

    def cond_value(self, event):
        return self.value

    def cond_cleanup(self):
        if isinstance(self.cond, DSProcess):
            self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
            sim.cleanup(self.cond)


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

    def cond_value(self, event):
        retval = {}
        for el in self.elements:
            if not el:
                continue
            if isinstance(el, DSFilter):
                retval[el] = el.cond_value(event)
            else:
                embedded = el.cond_value(event)
                retval.update(embedded)
        return retval
    
    def cond_cleanup(self):
        for el in self.elements:
            el.cond_cleanup()

    def __bool__(self):
        return self.expression(self.elements)

    def __str__(self):
        strings = [str(v) for v in self.elements]
        expression = '|' if self.expression == any else '&'
        return '(' + f' {expression} '.join(strings) + ')'

    def __call__(self, event):
        ''' Handles logic for the event. '''
        # First, we update all the elements.
        for el in self.elements:
            el(event)
        # And then we compute the expression.
        # Note- another approach would be if we would immediatelly compute the expression.
        # For instance, if we had an instance of any(A, B, C, ...) and we update A whose
        # expression would afterwards compute as True (satisfied), we would not need to
        # update others (B, C, ...).
        # The limitation of such solution is that it could not be applied to expressions
        # which have DFilter(reevaluate=True). This is the reason why it's implemented
        # this way.
        retval = self.expression(self.elements)
        return retval
