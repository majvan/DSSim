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
from dssim.base import NumericType, TimeType, EventType, CondType, SignalMixin, DSAbortException
from dssim.pubsub import DSConsumer, DSProducer, DSCallback


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


StateType = Any
LogEntry = Tuple[NumericType, StateType]
BinType = NumericType
StateToBinConverter = Callable[[StateType], BinType]
EventToStateConverter = Callable[[Optional[EventType]], StateType]

class ProbeBase(DSConsumer):
    @abstractmethod
    def send(self, event: EventType) -> None:
        raise NotImplementedError('Implement this in a derived class.')
    
    @abstractmethod
    def print_statistics(self,
                         filter_zero_transitions: bool = True,
                         bin_converter: StateToBinConverter = lambda state: state,
                         ) -> None:
        raise NotImplementedError('Implement this in a derived class.')


class DSProbe(ProbeBase):
    ''' The probe is used for monitoring states.
    '''
    def __init__(self, event_to_state: EventToStateConverter, ep: DSProducer, initial_state: Optional[StateType] = None, *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        name = kwargs.pop('name', ep.name+'.probe')
        super().__init__(name=name, cond=lambda e:True, *args, **kwargs)
        self._log: List[self.__class__.LogEntry] = []
        self._ep = ep
        self._ep.add_subscriber(self, phase='pre')
        # self._ep.add_subscriber(cb, phase='post+')
        # self._ep.add_subscriber(cb, phase='post-')
        self._event_to_state = event_to_state
        self._last_state = initial_state
        if initial_state is not None:
            self._log.append((self.sim.time, initial_state)) # self._last_state = initial_state

    def send(self, event: EventType) -> None:
        state = self._event_to_state(event)
        if self._last_state != state:
            self._last_state = state
            self._log.append((self.sim.time, state))
    
    def print_statistics(self,
                         filter_zero_transitions: bool = True,
                         filter_zero_deltas: bool = True,
                         duration_stat: bool = True,
                         bin_converter: StateToBinConverter = lambda state: state,
                        #  caption: Optional[str] = None
                         ) -> None:
        # first, compute time deltas
        deltas: List[self.__class__.LogEntry] = []

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

        # filter out zero delta states
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
            cummulative[bin_converter(state)] = cummulative.get(state, 0) + time
            total += time
            if time != 0:
                cummulative_n0[bin_converter(state)] = cummulative_n0.get(state, 0) + time
                total_n0 += time

        print(str(self))
        print("{:10s} {:^27s} | {:^27s}".format(
            "",
            "Distribution",
            "Non-zero distribution",
        ))
        print("{:10s} {:>20s} {:>6s} | {:>20s} {:>6s}".format(
            "State",
            "Duration",
            "%",
            "Duration",
            "%",
        ))
        for bin in cummulative.keys():
            print("{:10s} {:20.3f} {:5.2f}% | {:20.3f} {:5.2f}%".format(
                str(bin),
                float(cummulative[bin]),
                cummulative[bin] * 100.0 / total,
                float(cummulative_n0[bin]),
                cummulative_n0[bin] * 100.0 / total_n0,
            ))
