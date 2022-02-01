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
from dssim.components.queue import Queue
from dssim.simulation import DSAbortException, sim, DSSchedulable, DSComponent

from random import randint

q = Queue(capacity=12)

class Person(DSComponent):
    def __init__(self, info, identifier, max_waiting_time, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.waiting_process = None

    def start_waiting(self, queue):
        self.queue = queue
        self.waiting_process = self.sim.schedule(0, self.wait_in_queue())

    def abort_waiting(self):
        if self.waiting_process:
            self.sim.abort(self.waiting_process)

    def wait_in_queue(self):
        try:
            wait = yield from sim.wait(self.max_waiting_time)
            self.queue.remove({'person': self})  # remove myself from the queue and return the waiting process
            try:
                first_person = None
                first_person = q.queue[0]['person']
            except Exception as e:
                pass
            print(f'{self.sim.time:<5} {self}: Giving up waiting in queue. First one is {first_person}')
        except DSAbortException as e:
            pass

    def __repr__(self):
        return f'Person{self.info}[{self.identifier}]'

    def __str__(self):
        return f'\033[0;34m{repr(self)}\033[0m' if self.info == 'EU' else f'\033[0;35m{repr(self)}\033[0m'

class VisaCheck(DSComponent):
    def __init__(self, info, identifier, queue, max_waiting_time, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.queue = queue
        self.sim.schedule(0, self.work())

    def work(self):
        while True:
            try:
                first_person = None
                first_person = q.queue[0]['person']
            except Exception as e:
                pass
            print(f'{self.sim.time:<5} {self}: Waiting for a person; first one is {first_person}')
            event = yield from self.queue.get(cond=lambda e:e['person'].info in self.info, timeout=self.max_waiting_time)
            if event is None:
                print(f'\033[0;31m{sim.time:<5} {self}: No person in the queue, closing.\033[0m')
                return
            person = event[0]['person']
            person.abort_waiting()  # abort his waiting process
            busy = randint(2, 6) if person.info == 'EU' else randint (5, 15)  # persons without EU visa take longer

            try:
                first_person = None
                first_person = q.queue[0]['person']
            except Exception as e:
                pass

            print(f'{sim.time:<5} {self}: Going to process {person} for {busy} minutes; first one is {first_person}')
            yield from sim.wait(busy)
            print(f'{sim.time:<5} {self}: {person} done.')

    def __repr__(self):
        return f'Check{self.info}[{self.identifier}]'


def eu_person_generator():
    i = 0
    while True:
        person = Person('EU', i, max_waiting_time=randint(10, 60))
        print(f'{sim.time:<5} {person}: Queueing with max. waiting time {person.max_waiting_time} at position {len(q)}.', end='')
        print(f' First one is thus \033[0;32m{person}\033[0m') if len(q) == 0 else print()
        person.start_waiting(q)
        queued = q.put_nowait({'person': person})
        if not queued:
            person.abort_waiting()
            print(f'{sim.time:<5} {person}: queue too long, giving up, I do not queue.')
        busy = randint(3, 6)
        yield from sim.wait(busy)
        i += 1

def ww_person_generator():
    i = 0
    while True:
        person = Person('WW', i, max_waiting_time=randint(20, 90))
        print(f'{sim.time:<5} {person}: Queueing with max. waiting time {person.max_waiting_time} at position {len(q)}.', end='')
        print(f' First one is thus \033[0;32m{person}\033[0m') if len(q) == 0 else print()
        person.start_waiting(q)
        queued = q.put_nowait({'person': person})
        if not queued:
            person.abort_waiting()
            print(f'{sim.time:<5} {person}: queue too long, giving up, I do not queue.')
        busy = randint(3, 6)
        yield from sim.wait(busy)
        i += 1

@DSSchedulable
def alien_person_generator():
    person = Person('Mars', 0, max_waiting_time=10000)
    print(f'{sim.time:<5} New Mars: Queueing {person} with max. waiting time {p.max_waiting_time} at position {len(q)}.')
    queued = q.put_nowait(person=person)
    if not queued:
        print(f'{sim.time:<5} New Mars: queue too long, {person} gave up and did not queue.')


persons = sim.schedule(0, eu_person_generator())
persons = sim.schedule(0, ww_person_generator())
#sim.schedule(300, alien_person_generator())

visa_checks = [VisaCheck('EU', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]
visa_checks = [VisaCheck('WW', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]

sim.run(10 * 60)
