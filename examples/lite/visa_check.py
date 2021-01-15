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
LiteLayer2 counterpart of examples/pubsub/visa_check.py.

Pubsub queue conditional waits are replaced with explicit wake signaling:
- producers and reneging persons signal clerks with "queue changed"
- each clerk checks whether the current head person is eligible
'''
from random import randint

from dssim import DSAbortException, DSSchedulable, DSComponent, DSSimulation, LiteLayer2

SIM_TIME = 60 * 10


def _notify_clerks() -> None:
    for clerk in all_checks:
        if not clerk.worker_process.finished():
            clerk.worker_process.signal('queue changed')


def _peek_head_item():
    return next(iter(q), None) if len(q) > 0 else None


def _purge_invalid_head() -> None:
    while len(q) > 0:
        item = _peek_head_item()
        if item is None:
            return
        person = item['person']
        if person.state == 'queued':
            return
        q.get_nowait()


def _first_person():
    _purge_invalid_head()
    item = _peek_head_item()
    return None if item is None else item['person']


class Person(DSComponent):
    def __init__(self, info, identifier, max_waiting_time):
        super().__init__()
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.waiting_process = None
        self.state = 'new'

    def start_waiting(self, queue):
        self.queue = queue
        self.state = 'queued'
        self.waiting_process = self.sim.process(self.wait_in_queue()).schedule(0)

    def abort_waiting(self):
        if self.waiting_process:
            self.waiting_process.abort()

    def wait_in_queue(self):
        try:
            wait = yield from sim.gwait(self.max_waiting_time)
            if wait is None and self.state == 'queued':
                self.state = 'reneged'
                print(f'{self.sim.time:<5} {self}: Giving up waiting in queue. First one is {_first_person()}')
                _notify_clerks()
        except DSAbortException:
            pass

    def __repr__(self):
        return f'Person{self.info}[{self.identifier}]'

    def __str__(self):
        return f'\033[0;34m{repr(self)}\033[0m' if self.info == 'EU' else f'\033[0;35m{repr(self)}\033[0m'


class VisaCheck(DSComponent):
    def __init__(self, info, identifier, queue, max_waiting_time):
        super().__init__()
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.queue = queue
        self.worker_process = self.sim.process(self.work()).schedule(0)
        self.stat = {'processed': 0}

    def _try_take_eligible(self):
        _purge_invalid_head()
        item = _peek_head_item()
        if item is None:
            return None
        person = item['person']
        if person.info not in self.info:
            return None
        q.get_nowait()
        if person.state != 'queued':
            return None
        person.state = 'processing'
        person.abort_waiting()
        _notify_clerks()
        return person

    def work(self):
        while True:
            print(
                f'{self.sim.time:<5} {self}: Waiting for a person '
                f'(timeout {self.max_waiting_time}); first one is {_first_person()}'
            )
            deadline = self.sim.time + self.max_waiting_time
            person = self._try_take_eligible()
            while person is None and self.sim.time < deadline:
                event = yield from sim.gwait(deadline - self.sim.time)
                if event is None:
                    break
                person = self._try_take_eligible()
            if person is None:
                print(f'\033[0;31m{sim.time:<5} {self}: No person in the queue, closing.\033[0m')
                return

            busy = randint(2, 6) if person.info == 'EU' else randint(5, 15)
            print(f'{sim.time:<5} {self}: Going to process {person} for {busy} minutes; first one is {_first_person()}')
            yield from sim.gwait(busy)
            print(f'{sim.time:<5} {self}: {person} done.')
            self.stat['processed'] += 1

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
            person.state = 'balked'
            person.abort_waiting()
            print(f'{sim.time:<5} {person}: queue too long, giving up, I do not queue.')
        else:
            _notify_clerks()
        busy = randint(3, 6)
        yield from sim.gwait(busy)
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
            person.state = 'balked'
            person.abort_waiting()
            print(f'{sim.time:<5} {person}: queue too long, giving up, I do not queue.')
        else:
            _notify_clerks()
        busy = randint(3, 6)
        yield from sim.gwait(busy)
        i += 1


@DSSchedulable
def alien_person_generator():
    person = Person('Mars', 0, max_waiting_time=10000)
    print(f'{sim.time:<5} New Mars: Queueing {person} with max. waiting time {person.max_waiting_time} at position {len(q)}.')
    queued = q.put_nowait({'person': person})
    if not queued:
        print(f'{sim.time:<5} New Mars: queue too long, {person} gave up and did not queue.')
    else:
        person.start_waiting(q)
        _notify_clerks()


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)

    q = sim.queue(capacity=12, name='queue')
    all_checks = []

    sim.schedule(0, eu_person_generator())
    sim.schedule(0, ww_person_generator())
    # sim.schedule(300, alien_person_generator())

    eu_visa_checks = [VisaCheck('EU', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]
    ww_visa_checks = [VisaCheck('WW', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]
    all_checks.extend(eu_visa_checks + ww_visa_checks)

    sim.run(SIM_TIME)
    print("Done.")
    total_processed = sum(check.stat['processed'] for check in eu_visa_checks + ww_visa_checks)

    assert total_processed > 120, f'The number of processed {total_processed} should be high'
