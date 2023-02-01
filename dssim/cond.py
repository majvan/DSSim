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
from dssim.simulation import DSProcess, DSCondition, DSCallback, DSSimulation

class DSFilter(DSCondition):
    def one_liner(self):
        return self.signaled

    def compile(self, other, expr):
        if (self.expression == expr) and (other.expression == expr):
            return DSFilterAggregated(expr, [self.signals] + [other.signals])
        if (other.expression == expr) and (self.expression == self.one_liner):
            self, other = other, self
        if (self.expression == expr) and (other.expression == other.one_liner):
            if self.reset == other.reset:
                self.signals.append(other)
                self.set_signals()
                return self
            # A reset circuit is mergeable only if it is one_liner. The reason
            # is that a reset circuit when signaled resets all his setters.
            if other.reset:
                self.signals.append(other)
                self.set_signals()
                return self
        return DSFilterAggregated(expr, [self, other])

    def set_signals(self):
        self.setters = list(filter(lambda s: not s.reset, self.signals))
        self.resetters = list(filter(lambda s: s.reset, self.signals))

    def __init__(self, cond=None, reevaluate=False, signal_timeout=False, sim=None):
        self.expression = self.one_liner
        self.signaled = False
        self.value = None
        self.cond = cond
        self.signals = [self]
        # Reevaluation means that after every event we receive we have to re-evaluate
        # the condition
        # If not reevaluation set, then once filter matches, it is flipped to signaled
        self.reevaluate = reevaluate
        self.reset = False
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
            # if inspect.getgeneratorstate(self.cond) == inspect.GEN_CREATED:
            self.cond = DSProcess(self.cond, sim=sim)  # convert to DSProcess so we could get return value
            # else:
            #     raise ValueError('Cannot filter already running generator.')
        if isinstance(self.cond, DSProcess):
            self.sim = self.cond.sim
            if not self.cond.started():
                self.cond = self.cond.schedule(0)  # start the process
            self.parent_process = self.sim.parent_process
            self.subscriber = DSCallback(self._process_finished, sim=self.sim)
            self.cond.finish_tx.add_subscriber(self.subscriber, 'pre')

    def make_reset(self):
        self.signaled = False

    def __or__(self, other):
        return self.compile(other, any)

    def __and__(self, other):
        return self.compile(other, all)
   
    def __neg__(self):
        self.reset = True
        return self

    def __str__(self):
        return f'DSFilter({self.cond})'

    def __bool__(self):
        return self.signaled

    def __call__(self, event):
        if self.signaled and not self.reevaluate:
            return True
        signaled, value = False, None
        if isinstance(self.cond, DSProcess):
            # now we should get this signaled only after return
            if self.cond.finished():
                if self.cond.value is None and self.signal_timeout:
                    signaled, value = True, None
                elif isinstance(self.cond.value, Exception):
                    pass
                else:
                    signaled, value = True, self.cond.value
            else:
                self.sim.send(self.cond, event)
        elif callable(self.cond) and self.cond(event):
            signaled, value = True, event
        elif self is event:
            signaled, value = True, event
        elif self.cond == event:
            signaled, value = True, event
        if not self.reset:
            # A resetting- circuit only pulses its signal, but does not keep the signal, neither value
            self.signaled, self.value = signaled, value
        return signaled

    def _process_finished(self, *args, **kwargs):
        # Following forces re-evaluation by injecting new event
        self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
        self.sim.send(self.parent_process, {'producer': self.cond, 'finished': True})

    def cond_value(self, event):
        return self.value

    def cond_cleanup(self):
        if isinstance(self.cond, DSProcess):
            self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
            self.sim.cleanup(self.cond)

    def get_process(self):
        return self.cond if isinstance(self.cond, DSProcess) else None


class DSFilterAggregated(DSFilter):
    def __init__(self, expression, signals):
        self.expression = expression
        self.signals = signals
        self.set_signals()
        self.reset = False
        self.signaled = False

    def make_reset(self):
        self.signaled = False
        for el in self.setters:
            el.signaled = False

    def __or__(self, other):
        return self.compile(other, any)

    def __and__(self, other):
        return self.compile(other, all)

    def __neg__(self):
        self.reset = True
        return self

    def cond_value(self, event):
        retval = {}
        for el in self.setters:
            if not el:
                continue
            if el.expression == el.one_liner:
                retval[el] = el.cond_value(event)
            else:
                embedded = el.cond_value(event)
                retval.update(embedded)
        return retval
    
    def cond_cleanup(self):
        for el in self.signals:
            el.cond_cleanup()

    def __bool__(self):
        self.signaled = len(self.setters) > 0 and self.expression(self.setters)
        return self.signaled

    def __str__(self):
        expression = '|' if self.expression == any else '&'
        strings = [str(v) for v in self.setters]
        retval = '(' + f' {expression} '.join(strings) + ')'
        if self.resetters:
            strings = ['-'+str(v) for v in self.resetters]
            retval = '(' + retval
            retval += f'({retval} & (' + f' {expression} '.join(strings) + '))'
        return retval

    def __call__(self, event):
        ''' Handles logic for the event. '''
        signaled = False
        if self.reset:
            # For resetting signals we check if they are signaled
            signaled = (len(self.setters) > 0) and self.expression(el(event) for el in self.setters)
            if signaled:
                # and if they are signaled, they reset the input setters
                for el in self.setters:
                    el.signaled = False
        else:
            # For normal (mixed signals) we check first if the logic of reseters reset the circuit
            if len(self.resetters) > 0:
                signaled = self.expression(el(event) for el in self.resetters)
            if signaled:
                # If they do, they reset the input setters
                for el in self.setters:
                    el.signaled = False
                signaled = False
            else:
                if len(self.setters) > 0:
                    results = [el(event) for el in self.setters]
                    signaled = self.expression(results)
        return signaled
