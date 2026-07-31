# Copyright 2026- majvan (majvan@gmail.com)
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
Base condition infrastructure and subscriber metadata for dssim framework.
Placed here (rather than base.py) to avoid circular imports: pubsub.py,
future.py, and process.py all need these definitions, while cond.py also
needs SubscriberMetadata — moving everything here breaks the
cond → pubsub → cond import cycle.
'''
from __future__ import annotations
from abc import abstractmethod
from typing import Any, Tuple, Callable, Union, Optional
from dssim.base import EventType, EventRetType


CondType = Union[Callable, Any,]


def AlwaysTrue(e: EventType) -> bool:
    return True

def AlwaysFalse(e: EventType) -> bool:
    return False


# Artificial object used for explicit pre-check paths in check_and_wait/check_and_gwait.
TestObject = object()


class ICondition:
    ''' An interface for a condition checkable classes '''
    __slots__ = ()

    @abstractmethod
    def check(self, event: EventType) -> Tuple[bool, Any]:
        raise NotImplementedError("The ICondition is an interface. Use derived class.")


class CallableConditionMixin:
    ''' Mixin that makes an ICondition subclass usable as a plain callable returning bool. '''
    __slots__ = ()

    def __call__(self, event: EventType) -> bool:
        # check() returns (signaled, value), we extract only the signaled info
        return self.check(event)[0]


class ITwoPhaseCondition(ICondition):
    ''' A side-effecting condition split into a pure guard and a commit.

    guard() only tests whether the operation could succeed now and, if so,
    claims the resource (bumping the channel's reserved-counters so sibling
    guards in the same pass see the claim). The circuit evaluator guards all
    branches first (pure pass), selects which branches fire (one for OR, all
    for AND), and only then commits the selected claims via commit_reserved() -
    releasing the rest via release_reserved(). This gives exactly-one semantics
    for OR and all-or-nothing for AND, which a check()-only condition cannot
    provide because check() commits at every evaluated branch.

    A claim lives only inside one synchronous circuit evaluation pass: it is
    either committed or released before the pass returns. Nothing else runs in
    between, so no persistence or timeout handling is needed. Because of that,
    a claim needs no identity of its own - the claimed size is derivable from
    the condition's fields, so guard() returns a plain bool and no per-claim
    object is ever allocated. A condition guarded k times in one pass (e.g.
    the same cond under two AND branches) owes exactly k commit_reserved() /
    release_reserved() calls, which the evaluator's plan guarantees.
    '''
    __slots__ = ()

    def guard(self, event: EventType) -> bool:
        ''' Pure test: claim the resource and return True when the operation
        could succeed now, else False. Must not mutate observable state (only
        internal reserved-counters, so that sibling guards in the same pass
        see the claim). Every successful guard() must be balanced by exactly
        one commit_reserved() or release_reserved() before the evaluation
        pass returns. '''
        raise NotImplementedError("The ITwoPhaseCondition is an interface. Use derived class.")

    def commit_reserved(self) -> Any:
        ''' Perform the operation claimed by the latest guard() and return
        its value. '''
        raise NotImplementedError("The ITwoPhaseCondition is an interface. Use derived class.")

    def release_reserved(self) -> None:
        ''' Drop the claim taken by the latest guard() without performing
        the operation. '''
        raise NotImplementedError("The ITwoPhaseCondition is an interface. Use derived class.")

    def check(self, event: EventType) -> Tuple[bool, Any]:
        ''' Single-phase compatibility: guard and commit immediately.
        Used when the condition stands alone (direct queue waits, a lone
        filter) where there is no arbitration to defer to. '''
        if not self.guard(event):
            return False, None
        return True, self.commit_reserved()


class StackedCond(ICondition):
    ''' A condition which can stack several simple conditions '''

    def __init__(self) -> None:
        self.conds: list[Any] = []
        self.value = None

    def push(self, cond: Any) -> "StackedCond":
        ''' Adds new condition to the stack '''
        self.conds.append(cond)
        return self

    def pop(self) -> Any:
        ''' Removes last condition from the stack '''
        return self.conds.pop()

    def check(self, event: EventType) -> Tuple[bool, EventType]:
        ''' Checks the stack.
        The event is passed to all the conditions on the stack till it finds the first one
        which passes.

        :returns: a result of pass check- a tuple (event_passed, value_of_event)
        '''
        # Exceptions bypass all conditions — check once before the loop.
        # retval never changes inside the loop (only mutated after break),
        # so this is equivalent to the per-iteration check that was here before.
        if isinstance(event, Exception):
            self.value = event
            return True, event
        signaled, retval = False, event
        for cond in self.conds:
            # ICondition first: its __call__ returns a tuple (always truthy), so it must
            # not fall through to the callable branch below.
            is_icond = isinstance(cond, ICondition)
            if is_icond:
                signaled, event = cond.check(retval)
            elif callable(cond) and cond(retval):  # plain lambda / function
                signaled, event = True, retval
            elif cond == retval:  # exact event match (e.g. None timeout sentinel)
                signaled, event = True, retval
            # else the event does not match our condition and hence will be ignored
            #     signaled, event = False, None  # not needed
            if signaled:
                if is_icond:  # reuse precomputed result — cond hasn't changed
                    retval = cond.cond_value()
                else:
                    retval = event
                self.value = retval
                break
        return signaled, retval

    def cond_value(self) -> Any:
        ''' Gets a representation of last passed event

        :returns: a value of the last event which passed the check
        '''
        return self.value


class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, publisher: Any = None, **info) -> None:
        super().__init__()
        self.publisher = publisher
        self.info = info


class DSTransferableCondition(ICondition):
    ''' A condition which can modify the event value '''

    def __init__(self, cond: CondType, transfer: Callable[[EventType], EventType] = lambda e:e) -> None:
        '''
        :param cond: The condition which is required to pass
        :param transfer: The callable which will be called when the check passes.
            The arg to the callable is the event. The return is the new value.
        '''

        self.cond = StackedCond().push(cond)
        self.transfer = transfer
        self.value = None

    def check(self, value):
        signaled, retval = self.cond.check(value)
        if signaled:
            retval = self.transfer(retval)
            self.value = retval
        return signaled, retval

    def cond_value(self) -> Any:
        return self.value


class SubscriberMetadata:
    def __init__(self):
        self.cond = StackedCond()
