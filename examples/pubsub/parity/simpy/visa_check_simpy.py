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
SimPy adaptation of examples/pubsub/visa_check.py.

Behavioral parity notes:
* Queue stores dict payloads: {'person': Person(...)}.
* Clerks process only when the head-of-queue person is eligible.
* Each person has an independent reneging timeout process.
* Queue changes wake waiting clerks via explicit notifier events.

Switch backend:
- --backend simpy (default)
- --backend dssim
'''
from __future__ import annotations

from random import randint
from _backend import import_simpy_backend

simpy, BACKEND = import_simpy_backend()

SIM_TIME = 60 * 10


class QueueChangeNotifier:
    '''Broadcast-like notifier for queue changes in SimPy.'''

    def __init__(self, env: simpy.Environment) -> None:
        self.env = env
        self._waiters: list[simpy.Event] = []

    def wait(self) -> simpy.Event:
        ev = self.env.event()
        self._waiters.append(ev)
        return ev

    def cancel(self, ev: simpy.Event) -> None:
        try:
            self._waiters.remove(ev)
        except ValueError:
            pass

    def notify(self) -> None:
        waiters = self._waiters
        self._waiters = []
        for ev in waiters:
            if not ev.triggered:
                ev.succeed(True)


def first_person() -> Person | None:
    try:
        return q[0]['person']
    except Exception:
        return None


class Person:
    def __init__(self, info: str, identifier: int, max_waiting_time: int, env: simpy.Environment):
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.env = env
        self.waiting_process: simpy.Process | None = None

    def start_waiting(self, queue: list[dict]) -> None:
        self.queue = queue
        self.waiting_process = self.env.process(self.wait_in_queue())

    def abort_waiting(self) -> None:
        if self.waiting_process is not None and self.waiting_process.is_alive:
            self.waiting_process.interrupt()

    def wait_in_queue(self):
        try:
            yield self.env.timeout(self.max_waiting_time)
            # remove myself from queue if still queued
            for i, item in enumerate(self.queue):
                if item.get('person') is self:
                    self.queue.pop(i)
                    break
            print(f'{self.env.now:<5} {self}: Giving up waiting in queue. First one is {first_person()}')
            queue_changed.notify()
        except simpy.Interrupt:
            pass

    def __repr__(self) -> str:
        return f'Person{self.info}[{self.identifier}]'

    def __str__(self) -> str:
        return f'\033[0;34m{repr(self)}\033[0m' if self.info == 'EU' else f'\033[0;35m{repr(self)}\033[0m'


class VisaCheck:
    def __init__(self, info: str, identifier: int, queue: list[dict], max_waiting_time: int, env: simpy.Environment):
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.queue = queue
        self.env = env
        self.stat = {'processed': 0}
        self.env.process(self.work())

    def _take_eligible_head(self) -> Person | None:
        if len(self.queue) == 0:
            return None
        person = self.queue[0]['person']
        if person.info not in self.info:
            return None
        self.queue.pop(0)
        queue_changed.notify()
        return person

    def work(self):
        while True:
            print(
                f'{self.env.now:<5} {self}: Waiting for a person '
                f'(timeout {self.max_waiting_time}); first one is {first_person()}'
            )
            deadline = self.env.now + self.max_waiting_time
            person = self._take_eligible_head()
            while person is None:
                remaining = deadline - self.env.now
                if remaining <= 0:
                    print(f'\033[0;31m{self.env.now:<5} {self}: No person in the queue, closing.\033[0m')
                    return
                queue_event = queue_changed.wait()
                timeout_event = self.env.timeout(remaining)
                events = yield queue_event | timeout_event
                if timeout_event in events and queue_event not in events:
                    queue_changed.cancel(queue_event)
                    print(f'\033[0;31m{self.env.now:<5} {self}: No person in the queue, closing.\033[0m')
                    return
                person = self._take_eligible_head()

            person.abort_waiting()
            busy = randint(2, 6) if person.info == 'EU' else randint(5, 15)
            print(f'{self.env.now:<5} {self}: Going to process {person} for {busy} minutes; first one is {first_person()}')
            yield self.env.timeout(busy)
            print(f'{self.env.now:<5} {self}: {person} done.')
            self.stat['processed'] += 1

    def __repr__(self) -> str:
        return f'Check{self.info}[{self.identifier}]'


def eu_person_generator(env: simpy.Environment):
    i = 0
    while True:
        person = Person('EU', i, max_waiting_time=randint(10, 60), env=env)
        print(f'{env.now:<5} {person}: Queueing with max. waiting time {person.max_waiting_time} at position {len(q)}.', end='')
        print(f' First one is thus \033[0;32m{person}\033[0m') if len(q) == 0 else print()
        person.start_waiting(q)
        if len(q) < QUEUE_CAPACITY:
            q.append({'person': person})
            queue_changed.notify()
        else:
            person.abort_waiting()
            print(f'{env.now:<5} {person}: queue too long, giving up, I do not queue.')
        busy = randint(3, 6)
        yield env.timeout(busy)
        i += 1


def ww_person_generator(env: simpy.Environment):
    i = 0
    while True:
        person = Person('WW', i, max_waiting_time=randint(20, 90), env=env)
        print(f'{env.now:<5} {person}: Queueing with max. waiting time {person.max_waiting_time} at position {len(q)}.', end='')
        print(f' First one is thus \033[0;32m{person}\033[0m') if len(q) == 0 else print()
        person.start_waiting(q)
        if len(q) < QUEUE_CAPACITY:
            q.append({'person': person})
            queue_changed.notify()
        else:
            person.abort_waiting()
            print(f'{env.now:<5} {person}: queue too long, giving up, I do not queue.')
        busy = randint(3, 6)
        yield env.timeout(busy)
        i += 1


def alien_person_generator(env: simpy.Environment):
    person = Person('Mars', 0, max_waiting_time=10000, env=env)
    print(f'{env.now:<5} New Mars: Queueing {person} with max. waiting time {person.max_waiting_time} at position {len(q)}.')
    if len(q) < QUEUE_CAPACITY:
        person.start_waiting(q)
        q.append({'person': person})
        queue_changed.notify()
    else:
        print(f'{env.now:<5} New Mars: queue too long, {person} gave up and did not queue.')


if __name__ == '__main__':
    env = simpy.Environment()
    QUEUE_CAPACITY = 12
    q: list[dict] = []
    queue_changed = QueueChangeNotifier(env)

    env.process(eu_person_generator(env))
    env.process(ww_person_generator(env))
    # env.process(alien_person_generator(env))

    eu_visa_checks = [VisaCheck('EU', i, q, max_waiting_time=randint(15, 30), env=env) for i in range(2)]
    ww_visa_checks = [VisaCheck('WW', i, q, max_waiting_time=randint(15, 30), env=env) for i in range(2)]

    print(f'Running... backend={BACKEND}')
    env.run(until=SIM_TIME)
    print("Done.")
    total_processed = sum(check.stat['processed'] for check in eu_visa_checks + ww_visa_checks)
    assert total_processed > 120, f'The number of processed {total_processed} should be high'
