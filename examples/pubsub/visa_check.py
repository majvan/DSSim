# Copyright 2021- majvan (majvan@gmail.com)
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
from dssim import DSAbortException, DSSchedulable, DSComponent, DSSimulation
from random import randint

SIM_TIME = 60 * 10


def first_person_in_queue(queue):
    try:
        return queue[0]['person']
    except Exception:
        return None


class Person(DSComponent):
    def __init__(self, info, identifier, max_waiting_time):
        super().__init__()
        self.info = info
        self.identifier = identifier
        self.max_waiting_time = max_waiting_time
        self.waiting_process = None

    def start_waiting(self, queue):
        self.queue = queue
        self.waiting_process = self.sim.process(self.wait_in_queue()).schedule(0)

    def abort_waiting(self):
        if self.waiting_process:
            self.waiting_process.abort()

    def wait_in_queue(self):
        try:
            yield from self.sim.gwait(self.max_waiting_time)
            self.queue.remove({'person': self})  # remove myself from the queue and return the waiting process
            print(f'{self.sim.time:<5} {self}: Giving up waiting in queue. First one is {first_person_in_queue(self.queue)}')
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
        self.sim.process(self.work()).schedule(0)
        self.stat = {'processed': 0}

    def work(self):
        while True:
            print(
                f'{self.sim.time:<5} {self}: Waiting for a person '
                f'(timeout {self.max_waiting_time}); first one is {first_person_in_queue(self.queue)}'
            )
            event = yield from self.queue.gget(cond=lambda e:e['person'].info in self.info, timeout=self.max_waiting_time)
            if event is None:
                print(f'\033[0;31m{sim.time:<5} {self}: No person in the queue, closing.\033[0m')
                return
            person = event['person']
            person.abort_waiting()  # abort his waiting process
            busy = randint(2, 6) if person.info == 'EU' else randint (5, 15)  # persons without EU visa take longer

            print(f'{sim.time:<5} {self}: Going to process {person} for {busy} minutes; first one is {first_person_in_queue(self.queue)}')
            yield from sim.gwait(busy)
            print(f'{sim.time:<5} {self}: {person} done.')
            self.stat['processed'] += 1

    def __repr__(self):
        return f'Check{self.info}[{self.identifier}]'


def person_generator(info, waiting_range):
    i = 0
    while True:
        person = Person(info, i, max_waiting_time=randint(*waiting_range))
        print(f'{sim.time:<5} {person}: Queueing with max. waiting time {person.max_waiting_time} at position {len(q)}.', end='')
        print(f' First one is thus \033[0;32m{person}\033[0m') if len(q) == 0 else print()
        queued = q.put_nowait({'person': person})
        if not queued:
            print(f'{sim.time:<5} {person}: queue too long, giving up, I do not queue.')
        else:
            person.start_waiting(q)
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


if __name__ == '__main__':
    sim = DSSimulation()

    q = sim.queue(capacity=12, name='queue')
    q_probe = q.add_stats_probe(name='users')

    sim.schedule(0, person_generator('EU', (10, 60)))
    sim.schedule(0, person_generator('WW', (20, 90)))
    #sim.schedule(300, alien_person_generator())

    eu_visa_checks = [VisaCheck('EU', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]
    ww_visa_checks = [VisaCheck('WW', i, q, max_waiting_time=randint(15, 30)) for i in range(2)]

    sim.run(SIM_TIME)
    print("Done.")
    all_checks = eu_visa_checks + ww_visa_checks
    total_processed = sum(check.stat['processed'] for check in all_checks)
    eu_processed = sum(check.stat['processed'] for check in eu_visa_checks)
    ww_processed = sum(check.stat['processed'] for check in ww_visa_checks)

    print(f"Summary: sim_time={sim.time}, queue_size={len(q)}")
    print(f"Summary: total_processed={total_processed}, eu_processed={eu_processed}, ww_processed={ww_processed}")
    q_stats = q_probe.get_statistics()
    print(
        f'Summary: {q_probe.name} '
        f'avg_len={q_stats["time_avg_len"]:.3f}, '
        f'max_len={q_stats["max_len"]}, '
        f'nonempty_ratio={q_stats["time_nonempty_ratio"]:.3f}, '
        f'puts={q_stats["put_count"]}, '
        f'gets={q_stats["get_count"]}'
    )
    for check in all_checks:
        print(f"Summary: {check} processed={check.stat['processed']}")

    assert total_processed > 120, f'The number of processed {total_processed} should be high'  # high probability to pass
