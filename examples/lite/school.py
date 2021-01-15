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
LiteLayer2 counterpart of examples/pubsub/school.py.

Because LiteLayer2 has no publisher/observer routing, the school explicitly
tracks currently attending pupil processes and signals bell events to them.
'''
from random import randint
from typing import Any

from dssim import DSComponent, DSSimulation, DSLiteAgent, LiteLayer2


DAY_MINUTES = 24 * 60


def fmt_hhmm(sim_time: float) -> str:
    minute_in_day = int(sim_time % DAY_MINUTES)
    return f'{minute_in_day // 60}:{minute_in_day % 60:02d}'


class School(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._listeners: list[Any] = []
        self.days = 0
        self.sim.schedule(0, self.school_bell())

    def register(self, pupil_process: Any) -> None:
        self._listeners.append(pupil_process)

    def unregister(self, pupil_process: Any) -> None:
        self._listeners = [p for p in self._listeners if p is not pupil_process]

    def _signal_bell(self, event: str) -> None:
        active = []
        for process in self._listeners:
            if not hasattr(process, 'finished') or not process.finished():
                process.signal(event)
                active.append(process)
        self._listeners = active

    def school_bell(self):
        while True:
            now = self.sim.time % DAY_MINUTES  # get time of day in [minutes]
            if now > 8 * 60:
                yield from self.sim.gsleep(DAY_MINUTES - now)  # wait till midnight
                now = 0
            yield from self.sim.gsleep(8 * 60 - now)  # wait till 8:00

            # Classes 1..9 with breaks; same timing as pubsub version.
            for break_minutes in (10, 20, 10, 10, 5, 10, 10, 10, None):
                self._signal_bell('start')
                yield from self.sim.gsleep(45)
                self._signal_bell('end')
                if break_minutes is None:
                    break
                yield from self.sim.gsleep(break_minutes)
            self.days += 1


class Pupil(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_classes = 0

    def go_to_school(self, school: School, nr_of_classes: int):
        print(f'{self} going to school at {fmt_hhmm(self.sim.time)}')

        class_n = 1
        while True:
            event = yield from self.sim.gwait()
            if event != 'start':
                continue
            print(f'{self} starting class #{class_n} at {fmt_hhmm(self.sim.time)}')

            # Wait for the corresponding class end bell.
            while True:
                event = yield from self.sim.gwait()
                if event == 'end':
                    break

            if class_n >= nr_of_classes:
                self.total_classes += nr_of_classes
                break

            class_n += 1
            print(f'{self} starting break at {fmt_hhmm(self.sim.time)}')

        # PubSub observe_pre scope ends here; in Lite we must unregister explicitly.
        school.unregister(self.sim.pid)

        print(f'{self} is after school at {fmt_hhmm(self.sim.time)}')
        minute_in_day = self.sim.time % DAY_MINUTES
        play_for = 21 * 60 - minute_in_day  # play after school till 21:00
        yield from self.sim.gsleep(play_for)
        print(f'{self} is going to sleep at {fmt_hhmm(self.sim.time)}')
        return 'done'


class Family(DSLiteAgent):
    def process(self, school: School, pupils: list[Pupil]):
        while True:
            now = self.sim.time % DAY_MINUTES  # get time of day in [minutes]
            yield from self.sim.gsleep(DAY_MINUTES - now)  # wait till midnight
            yield from self.sim.gsleep(7 * 60 + 45)  # wait till 7:45
            for pupil in pupils:
                process = self.sim.process(pupil.go_to_school(school, randint(6, 8))).schedule(0)
                school.register(process)


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    school = School(name='Elementary School Newton Street', sim=sim)
    pupils = [Pupil(name=pupil_name, sim=sim) for pupil_name in ('Peter', 'John', 'Maria', 'Eva')]
    Family(school, pupils, name='Family', sim=sim)

    sim.run(24 * 60 * 30)
    assert 180 <= pupils[0].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[1].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[2].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[3].total_classes <= 220  # high probability to get into interval
