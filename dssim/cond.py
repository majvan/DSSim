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
import copy
from dssim.simulation import DSCallback, DSFuture, DSProcess, ICondition

class DSFilter(DSFuture, ICondition):
    ''' Differences from DSFuture:
    1. DSFilter can be reevaluated, i.e. the finished() is not monostable. It can
    once return True and the next call return False (if reevaluate is True).
    2. DSFilter can be pulsed, i.e. the finished() never returns True, but the call
    to DSFilter can return True (signaled). This requires the filter to be reevaluated.
    3. DSFilter can be negated. This is possible: filter = -DSFilter(...).
    Such expression will always change the filter policy to be pulsed.
    4. DSFilter forwards all the events to the wrapped DSProcess.
    '''
    class SignalType:
        DEFAULT = 0  # Monostable. If once signaled, always signaled
        REEVALUATE = 1  # Reevaluated after every event, i.e. the value changes after every event
        PULSED = 2  # Returns "signaled" only when __call__(event) matches, but never stays in the state

    ONE_LINER = 'one liner'

    def __init__(self, cond=None, sigtype=SignalType.DEFAULT, signal_timeout=False, forward_events=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expression = self.ONE_LINER
        self.signals = [self]
        self.positive = True  # positive sign
        self.signaled = False
        self.value = None
        self.cond = cond
        # Reevaluation means that after every event we receive we have to re-evaluate
        # the condition
        # If not reevaluation set, then once filter matches, it is flipped to signaled
        self.pulse = sigtype in (self.SignalType.PULSED,)
        self.reevaluate = sigtype in (self.SignalType.REEVALUATE, self.SignalType.PULSED,)
        # Signalling timeout is for generators. If a generator returns with None, this means
        # that it timed out. If signal_timeout is True, such timeout would be understood
        # as a valid signal.
        self.signal_timeout = signal_timeout
        if inspect.isgenerator(self.cond) or inspect.iscoroutine(self.cond):
            # We create a new process from generator
            self.cond = DSProcess(self.cond, sim=self.sim)  # convert to DSProcess so we could get return value
            # It is assumed that the coro / generator runs in the same 'context' as the current process.
            # The coro / generator gets events which were planned for the current running process by default.
            self.forward_events = (forward_events != False)  # True => True, None => True, False => False
        else:
            self.forward_events = (forward_events == True)  # True => True, None => False, False => False
        if isinstance(self.cond, DSProcess):
            self.sim = self.cond.sim
            if not self.cond.started():
                self.cond = self.cond.schedule(0)  # start the process

    def __or__(self, other):
        return DSFilterAggregated.build(self, other, any)

    def __and__(self, other):
        return DSFilterAggregated.build(self, other, all)
   
    def __neg__(self):
        if not self.positive:
            raise ValueError('You can negate a DSFilter only once')
        f = copy.copy(self)
        f.pulse, f.reevaluate = True, True
        f.positive = False
        return f

    def __str__(self):
        retval = f'DSFilter({self.cond})'
        if not self.positive:
            retval = '-' + retval
        return retval

    def finished(self):
        return self.signaled
    
    def __call__(self, event):
        ''' Tries to evaluate the event. '''
        if self.signaled and not self.reevaluate:
            return True
        signaled, value = False, None
        if isinstance(self.cond, DSFuture):
            # now we should get this signaled only after return
            if self.forward_events:
                # forward message to the consumer
                self.sim.send(self.cond, event)
            if self.cond.finished():
                if self.cond.exc is not None:
                    pass
                elif self.cond.value is None and self.signal_timeout:
                    signaled, value = True, None
                elif self.pulse:
                    signaled, value = (event == self.cond), event
                else:
                    signaled, value = True, self.cond.value
        elif self.cond == event:
            signaled, value = True, event
        elif callable(self.cond) and self.cond(event):
            signaled, value = True, event
        # elif self is event:
        #     signaled, value = True, event
        if not self.pulse:
            # A resetting- circuit only pulses its signal, but does not keep the signal, neither value
            self.signaled = signaled
        if signaled:
            self._finish(value, async_future=False)
        return signaled

    def get_future_eps(self):
        retval = {self._finish_tx,}
        if isinstance(self.cond, DSFuture):
            retval |= self.cond.get_future_eps()
        return retval

    def finish(self, value):
        self._finish(value, async_future=True)

    def _finish(self, value, async_future):
        self.value = value
        if not self.pulse:
            self.signaled = True
        if async_future:
            # Following forces re-evaluation by injecting new event.
            # We have to re-evaluate only when finish() was called asynchronously.
            self._finish_tx.signal(self)

    def cond_value(self, event):
        return self.value

    def get_process(self):
        return self.cond if isinstance(self.cond, DSProcess) else None        


class DSFilterAggregated(DSFuture, ICondition):
    ''' DSFilterAggregated aggregates several DSFutures into AND / OR circuit.
    It evaluates the circuit after every event. The finished()
    1. DSFilter can be reevaluated, i.e. the finished() is not monostable. It can
    once return True and the next call return False (if reevaluate is True).
    2. DSFilter can be pulsed, i.e. the finished() never returns True, but the call
    to DSFilter can return True (signaled). This requires the filter to be reevaluated.
    3. DSFilter can be negated. This is possible: filter = -DSFilter(...).
    Such expression will always change the filter policy to be pulsed.
    '''

    def __init__(self, expression, signals, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expression = expression
        self.signals = signals
        self.set_signals()
        self.positive = True
        self.signaled = False
        # The sim is required for awaitable
        self.sim = self.signals[0].sim  # get the sim from the first signal

    @staticmethod
    def build(first, second, expr):
        if (first.expression == expr) and (second.expression == expr):
            return DSFilterAggregated(expr, [first.signals] + [second.signals])
        if (second.expression == expr) and (first.expression == DSFilter.ONE_LINER):
            first, second = second, first
        if (first.expression == expr) and (second.expression == DSFilter.ONE_LINER):
            if first.positive == second.positive:
                first.signals.append(second)
                first.set_signals()
                return first
            # A reset circuit is mergeable only if it is one_liner. The reason
            # is that a reset circuit when signaled resets all his setters.
            if not second.positive:
                first.signals.append(second)
                first.set_signals()
                return first
        return DSFilterAggregated(expr, [first, second])

    def set_signals(self):
        self.setters, self.resetters = [], []
        for s in self.signals:
            if s.positive:
                self.setters.append(s)
            else:
                self.resetters.append(s)

    def __or__(self, other):
        return DSFilterAggregated.build(self, other, any)

    def __and__(self, other):
        return DSFilterAggregated.build(self, other, all)

    def __neg__(self):
        self.positive = False
        return self

    def cond_value(self, event):
        retval = {}
        for el in self.setters:
            if not el.finished():
                continue
            if isinstance(el, DSFilterAggregated):
                embedded = el.cond_value(event)
                retval.update(embedded)
            elif hasattr(el, 'cond_value'):
                retval[el] = el.cond_value(event)
            else:
                retval[el] = el.value
        return retval
    
    def __str__(self):
        expression = ' | ' if self.expression == any else ' & '
        strings = [str(v) for v in self.setters + self.resetters]
        retval = expression.join(strings)
        sign = '' if self.positive else '-'
        return f'{sign}({retval})'

    def finished(self):
        return self.signaled
    
    def _gather_results(self, event, futures):
        retval = []
        for fut in futures:
            if isinstance(fut, DSFilter) or isinstance(fut, DSFilterAggregated):
                retval.append(fut(event))
            else:
                retval.append(fut.finished())
        return retval

    def get_future_eps(self):
        retval = set()
        for s in self.signals:
            retval |= s.get_future_eps()
        return retval

    def __call__(self, event):
        ''' Handles logic for the event. Pushes the event to the inputs and then evaluates the circuit. '''
        signaled = False
        # In the following, we have to send the event to the whole circuit. The reason is that
        # once some gate is signaled, it could be reset later; however if the signal stops event
        # to be spread to other gates; the other gates could be activated as well with the same
        # event.
        if not self.positive:
            # For resetting signals we check if they are signaled
            if len(self.setters) > 0:
                results = self._gather_results(event, self.setters)
                signaled = self.expression(results)
            if signaled:
                # and if they are signaled, they reset the input setters
                for el in self.setters:
                    el.signaled = False
        else:
            # For normal (mixed signals) we check first if the logic of reseters reset the circuit
            if len(self.resetters) > 0:
                results = self._gather_results(event, self.resetters)
                reset_signal = self.expression(results)
            else:
                reset_signal = False
            if reset_signal:
                # If they do, they reset the input setters
                for el in self.setters:
                    el.signaled = False
                signaled = False
            else:
                if len(self.setters) > 0:
                    results = self._gather_results(event, self.setters)
                    signaled = self.expression(results)
            self.signaled = signaled
            if signaled:
                self.finish(self.cond_value(event))
        return signaled
    
