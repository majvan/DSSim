# Copyright 2020 NXP Semiconductors
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
Easy propagation delay component. The original producer is preserved at the
producer output.
'''
from typing import Any
from dssim.base import EventType, DSComponent
from dssim.pubsub import DSCallback, DSProducer


class Delay(DSComponent):
    ''' Delay component which delays event by a constant time '''
    def __init__(self, delay: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_delay(delay)
        self.rx = self.sim.callback(self._on_event, name=self.name + '.rx')
        self.tx = self.sim.producer(name=self.name + '.tx')

    def set_delay(self, delay: float) -> None:
        ''' Set the delay '''
        self.delay = delay or 0

    def _on_event(self, event: EventType) -> None:
        ''' Consumer which feeds the output after the programmed delay '''
        self.tx.schedule_event(self.delay, event)
