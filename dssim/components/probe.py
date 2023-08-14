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
The file implements container and queue components.
'''
from typing import Any, List, Dict, Tuple, Optional, Tuple, Callable, TYPE_CHECKING
from abc import abstractmethod
from enum import Enum
from dssim.base import NumericType, TimeType, EventType, CondType, SignalMixin, DSAbortException
from dssim.pubsub import DSConsumer, DSProducer, DSCallback


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


StateType = Any
BinType = NumericType
StateToBinConverter = Callable[[StateType], BinType]
EventToStateConverter = Callable[[Optional[EventType]], StateType]

class ProbeBase(DSConsumer):
    ''' The probe is used for logging activity of an endpoint.
    '''
    LogEntry = Tuple[NumericType, StateType]
    def __init__(self,
                 ep: DSProducer,
                 event_to_state: EventToStateConverter = lambda e:e,
                 *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        name = kwargs.pop('name', ep.name+'.probe')
        super().__init__(name=name, cond=lambda e:True, *args, **kwargs)
        self._log: List = []
        self._ep = ep
        self._ep.add_subscriber(self, phase='pre')
        self._event_to_state = event_to_state

    def print_cummulatives(self, cummulative, total, cummulative_n0, total_n0):
        print(str(self))
        print("{:10s} {:^28s} | {:^28s}".format(
            "",
            "State duration",
            "Non-zero state duration",
        ))
        print("{:10s} {:>20s} {:>7s} | {:>20s} {:>7s}".format(
            "State",
            "Duration",
            "%",
            "Duration",
            "%",
        ))
        for bin in sorted(cummulative.keys()):
            if bin:
                print("{:10s} {:20.3f} {:6.2f}% | {:20.3f} {:6.2f}%".format(
                    str(bin),
                    float(cummulative[bin]),
                    cummulative[bin] * 100.0 / total,
                    float(cummulative_n0[bin]),
                    cummulative_n0[bin] * 100.0 / total_n0,
                ))
            else:
                print("{:10s} {:20.3f} {:6.2f}% |".format(
                    str(bin),
                    float(cummulative[bin]),
                    cummulative[bin] * 100.0 / total,
                ))

    @abstractmethod
    def send(self, obj: Any) -> None:
        raise NotImplementedError('Implement this in a derived class.')
    
    @abstractmethod
    def print_statistics(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError('Implement this in a derived class.')


class DSProbe(ProbeBase):
    ''' The basic probe which stores a state in certain time.
    '''
    LogEntry = Tuple[NumericType, StateType]
    def __init__(self,
                 ep: DSProducer,
                 event_to_state: EventToStateConverter = lambda e:e,
                 initial_state: Optional[StateType] = None,
                 *args: Any, **kwargs: Any) -> None:
        ''' Init probe '''
        super().__init__(ep, event_to_state, *args, **kwargs)
        self._last_state = initial_state
        self._log.append((self.sim.time, initial_state))

    def send(self, event: EventType) -> None:
        state = self._event_to_state(event)
        self._log.append((self.sim.time, state))
    
    def print_statistics(self,
                         filter_zero_transitions: bool = True,
                         filter_zero_deltas: bool = True,
                         duration_stat: bool = True,
                         bin_converter: StateToBinConverter = lambda state: state,
                         ) -> None:
        # filter out zero duration transitions
        if filter_zero_transitions:
            input, output = self._log, []
            if len(input) > 0:
                last_time, last_state = input[0]
                for time, state in input[1:]:
                    if last_time != time:
                        output.append((last_time, last_state))
                        last_time = time
                    last_state = state
                output.append((last_time, last_state))
        else:
            output = self._log

        # filter out changes to the same state
        if filter_zero_deltas:
            input, output = output, []
            if len(input) > 0:
                last_time, last_state = input[0]
                for time, state in input[1:]:
                    if last_state != state:
                        output.append((last_time, last_state))
                        last_time = time
                    last_state = state
                output.append((last_time, last_state))

        # compute time deltas for abs time probes
        states = set()
        input, output = output, []
        if len(input) > 0:
            last_time, last_state = input[0]
            for time, state in input[1:]:
                if duration_stat:
                    output.append((time - last_time, last_state))
                else:
                    output.append((1, last_state))
                states.add(last_state)
                last_time, last_state = time, state
            if duration_stat:
                output.append((self.sim.time - time, state))
            else:
                output.append((1, state))
            states.add(state)

        deltas = output

        cummulative: Dict[NumericType, NumericType] = {}
        total: float = 0
        cummulative_n0: Dict[NumericType, NumericType] = {}
        total_n0: float = 0
        for time, state in deltas:
            bin = bin_converter(state)
            cummulative[bin] = cummulative.get(state, 0) + time
            total += time
            if bin:
                cummulative_n0[bin] = cummulative_n0.get(state, 0) + time
                total_n0 += time

        self.print_cummulatives(cummulative, total, cummulative_n0, total_n0)


class DSDurationProbe(ProbeBase):
    ''' The basic probe which stores a state in certain time.
    '''
    LogEntry = Tuple[NumericType, StateType]
    def send(self, obj: Dict[NumericType, Any]) -> None:
        self._log.append(obj)
    
    def print_statistics(self,
                         /,
                         filter_zero_transitions: bool = True,
                         filter_zero_deltas: bool = False,
                         bin_converter: StateToBinConverter = lambda state: state,
                         duration_stat: bool = True,
                         ) -> None:
        # filter out zero duration transitions
        if filter_zero_transitions:
            input, output = self._log, []
            for time, obj in input:
                if time > 0:
                    output.append((time, obj))

        # filter out changes to the same state: merge durations
        if filter_zero_deltas:
            input, output = output, []
            if len(input) > 0:
                last_time, last_state = input[0]
                for time, state in input[1:]:
                    if last_state != state:
                        output.append((last_time, last_state))
                        last_time, last_state = time, state
                    else:
                        last_time += time
                output.append((last_time, last_state))

        # compute time deltas for abs time probes
        states = set()
        if len(input) > 0:
            for time, state in input:
                states.add(state)
        deltas = output

        cummulative: Dict[NumericType, NumericType] = {}
        total: float = 0
        cummulative_n0: Dict[NumericType, NumericType] = {}
        total_n0: float = 0
        for time, state in deltas:
            bin = bin_converter(state)
            cummulative[bin] = cummulative.get(state, 0) + time
            total += time
            if bin:
                cummulative_n0[bin] = cummulative_n0.get(state, 0) + time
                total_n0 += time

        self.print_cummulatives(cummulative, total, cummulative_n0, total_n0)


class DSIdleProbe(ProbeBase):
    ''' The basic probe which stores a state in certain time.
    '''
    LogEntry = Dict
    def __init__(self,
                 ep: DSProducer,
                 event_to_state: EventToStateConverter = lambda e:e,
                 *args: Any,
                 **kwargs: Any) -> None:
        super().__init__(ep, event_to_state, *args, **kwargs)
        self._len = 0
        self._last_time = 0

    def send(self, log_object: Dict) -> None:
        self._log.append(log_object)
    
    def print_statistics(self,
                         filter_zero_transitions: bool = True,
                         filter_zero_deltas: bool = False,
                         bin_converter: StateToBinConverter = lambda state: state,
                         duration_stat: bool = True,
                        #  caption: Optional[str] = None
                         ) -> None:
        # compute time deltas and length of the waiting queue
        input, output = self._log, []
        length, last_time = 0, 0
        for record in input:
            output.append((record['time'] - last_time, length))
            if record['op'] == 'enter':
                length += 1  # length of waiting tasks
            if record['op'] == 'exit':
                length -= 1  # length of waiting tasks
            last_time = record['time']

        # filter out zero duration transitions
        if filter_zero_transitions:
            input, output = output, []
            for time, obj in input:
                if time > 0:
                    output.append((time, obj))

        # filter out changes to the same state: merge durations
        if filter_zero_deltas:
            input, output = output, []
            if len(input) > 0:
                last_time, last_state = input[0]
                for time, state in input[1:]:
                    if last_state != state:
                        output.append((last_time, last_state))
                        last_time, last_state = time, state
                    else:
                        last_time += time
                output.append((last_time, last_state))

        # compute time deltas for abs time probes
        states = set()
        if len(input) > 0:
            for time, state in input:
                states.add(state)
        deltas = output

        cummulative: Dict[NumericType, NumericType] = {}
        total: float = 0
        cummulative_n0: Dict[NumericType, NumericType] = {}
        total_n0: float = 0
        for time, state in deltas:
            bin = bin_converter(state)
            cummulative[bin] = cummulative.get(state, 0) + time
            total += time
            if bin:
                cummulative_n0[bin] = cummulative_n0.get(state, 0) + time
                total_n0 += time

        self.print_cummulatives(cummulative, total, cummulative_n0, total_n0)
