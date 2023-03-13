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
from dssim.simulation import DSProcess, ICondition, DSCallback, DSFuture


class DSCondition(DSFuture):
    ONE_LINER = 'one liner'

    def __await__(self):
        with self.sim.observe_pre(self.finish_tx):
            retval = yield from self.sim.check_and_gwait(cond=self)
        if self.exc is not None:
            raise self.exc
        return self.value    

    def finish(self, value):
        # The conditions do not send signals to other processes, so no finish_tx activity
        self.value = value
        self.sim.cleanup(self)
		
    def fail(self, exc):
        # The conditions do not send signals to other processes, so no finish_tx activity
        self.exc = exc
        self.sim.cleanup(self)


class DSFilter(DSCondition, ICondition):
    ''' Differences from DSFuture:
    1. DSFilter can be reevaluated, i.e. the finished() is not monostable. It can
    once return True and the next call return False (if reevaluate is True).
    2. DSFilter can be pulsed, i.e. the finished() never returns True, but the call
    to DSFilter can return True (signaled). This requires the filter to be reevaluated.
    3. DSFilter can be negated. This is possible: filter = -DSFilter(...).
    Such expression will always change the filter policy to be pulsed.
    4. DSFilter forwards all the events to the wrapped cond.
    '''
    class Policy:
        DEFAULT = 0
        REEVALUATE = 1
        PULSED = 2

    def __init__(self, cond=None, policy=Policy.DEFAULT, signal_timeout=False, *args, **kwargs):
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
        self.pulse = policy in (self.Policy.PULSED,)
        self.reevaluate = policy in (self.Policy.REEVALUATE, self.Policy.PULSED,)
        # Signalling timeout is for generators. If a generator returns with None, this means
        # that it timed out. If signal_timeout is True, such timeout would be understood
        # as a valid signal.
        self.signal_timeout = signal_timeout
        if inspect.isgenerator(self.cond) or inspect.iscoroutine(self.cond):
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
            self.cond = DSProcess(self.cond, sim=self.sim)  # convert to DSProcess so we could get return value
            # else:
            #     raise ValueError('Cannot filter already running generator.')
        if isinstance(self.cond, DSProcess):
            self.sim = self.cond.sim
            if not self.cond.started():
                self.cond = self.cond.schedule(0)  # start the process
            self.parent_process = self.sim.parent_process
        if isinstance(self.cond, DSFuture):
            self.subscriber = DSCallback(self._process_finished, sim=self.sim)
            self.cond.finish_tx.add_subscriber(self.subscriber, 'pre')

    def __or__(self, other):
        return DSFilterAggregated.build(self, other, any)

    def __and__(self, other):
        return DSFilterAggregated.build(self, other, all)
   
    def __neg__(self):
        self.pulse, self.reevaluate = True, True
        self.positive = False
        return self

    def __str__(self):
        return f'DSFilter({self.cond})'

    def finished(self):
        return self.signaled
    
    def __call__(self, event):
        ''' Tries to evaluate the event. '''
        if self.signaled and not self.reevaluate:
            return True
        signaled, value = False, None
        if isinstance(self.cond, DSFuture):
            # now we should get this signaled only after return
            if isinstance(self.cond, DSProcess):
                # forward message to the child process
                self.sim.send(self.cond, event)
            if self.cond.finished():
                if self.cond.exc is not None:
                    pass
                elif self.cond.value is None and self.signal_timeout:
                    signaled, value = True, None
                else:
                    signaled, value = True, self.cond.value
        elif callable(self.cond) and self.cond(event):
            signaled, value = True, event
        elif self is event:
            signaled, value = True, event
        elif self.cond == event:
            signaled, value = True, event
        if not self.pulse:
            # A resetting- circuit only pulses its signal, but does not keep the signal, neither value
            self.signaled = signaled
        if signaled:
            self.finish(value)
        return signaled

    def _process_finished(self, future):
        if not self.reevaluate:
            self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
        # Following forces re-evaluation by injecting new event
        self.sim.send(self.parent_process, future)

    def cond_value(self, event):
        return self.value

    def cond_cleanup(self):
        if isinstance(self.cond, DSFuture):
            self.cond.finish_tx.remove_subscriber(self.subscriber, 'pre')
            self.sim.cleanup(self.cond)

    def get_process(self):
        return self.cond if isinstance(self.cond, DSProcess) else None        


class DSFilterAggregated(DSCondition, ICondition):
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
    def _has_expr(filt, expr):
        return isinstance(filt, DSFilterAggregated) and filt.expression == expr

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
            if not isinstance(s, DSCondition):
                self.setters.append(s)
            elif s.positive:
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
    
    def cond_cleanup(self):
        for el in self.signals:
            el.cond_cleanup()

    def __str__(self):
        expression = '|' if self.expression == any else '&'
        strings = [str(v) for v in self.setters]
        retval = '(' + f' {expression} '.join(strings) + ')'
        if self.resetters:
            strings = ['-'+str(v) for v in self.resetters]
            retval = '(' + retval
            retval += f'({retval} & (' + f' {expression} '.join(strings) + '))'
        return retval

    def finished(self):
        return self.signaled

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
                results = [el(event) for el in self.setters]
                signaled = self.expression(results)
            if signaled:
                # and if they are signaled, they reset the input setters
                for el in self.setters:
                    el.signaled = False
        else:
            # For normal (mixed signals) we check first if the logic of reseters reset the circuit
            if len(self.resetters) > 0:
                results = [el(event) for el in self.resetters]
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
                    results = [el(event) for el in self.setters]
                    signaled = self.expression(results)
            self.signaled = signaled
            if signaled:
                self.finish(self.cond_value(event))
        return signaled
    
