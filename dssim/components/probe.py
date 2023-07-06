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
from dssim.base import NumericType, TimeType, EventType, CondType, SignalMixin, DSAbortException
from dssim.pubsub import DSConsumer, DSProducer, DSCallback


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


LogEntry = Tuple[NumericType, NumericType]
NumToBinConverter = Callable[[NumericType], NumericType]

class Probe(DSConsumer):
    ''' The probe is simply used for monitoring events.
    '''
    def __init__(self, logging_fcn: Callable[[Optional[EventType]], NumericType], ep: DSProducer, initial_val: NumericType = 0, *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        name=kwargs.pop('name', ep.name+'.probe')
        super().__init__(name=name, *args, **kwargs)
        self._log: List[LogEntry] = []
        self._ep = ep
        cb = self.sim.callback(self.log_state, name=self.name+'.cb')
        self._ep.add_subscriber(cb, phase='pre')
        # self._ep.add_subscriber(cb, phase='post+')
        # self._ep.add_subscriber(cb, phase='post-')
        self._logging_fcn = logging_fcn
        self._log.append((self.sim.time, initial_val)) # self._last_state = initial_val

    def log_state(self, event: EventType) -> None:
        state = self._logging_fcn(event)
        if True: # self._last_state != state:
            self._last_state = state
            self._log.append((self.sim.time, state))
    
    def print_statistics(self,
                         filter_zero_transitions: bool = True,
                         bin_converter: NumToBinConverter = lambda state: state,
                        #  caption: Optional[str] = None
                         ) -> None:
        # first, compute time deltas
        deltas: List[LogEntry] = []

        if filter_zero_transitions:
            input, output = self._log, []
            last_time, last_state = input[0]
            for time, state in input[1:]:
                if last_time != time:  # transitions which led to the same state are omitted
                    output.append((last_time, last_state))
                    last_time = time
                last_state = state
            output.append((last_time, last_state))
        else:
            output = self._log

        input, output = output, []
        last_time, last_state = input[0]
        for time, state in input[1:]:
            if last_state != state:  # transitions which led to the same state are omitted
                output.append((last_time, last_state))
                last_time = time
            last_state = state
        output.append((last_time, last_state))

        states = set()
        input, output = output, []
        last_time, last_state = input[0]
        for time, state in input[1:]:
            output.append((time - last_time, last_state))
            states.add(last_state)
            last_time, last_state = time, state
        output.append((self.sim.time - time, state))
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
