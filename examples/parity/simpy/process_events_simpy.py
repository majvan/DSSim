# Copyright 2020- majvan (majvan@gmail.com)
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
SimPy adaptation of process_events.py.

Key differences from the DSSim version:

* simpy.Environment replaces DSSimulation; no DSComponent base class needed.
* Attacker-to-locker communication uses a simpy.Store (mailbox) instead of
  sim.signal() / DSProcess signalling.
* _wait_for_code() manually implements condition-filtered timeout wait via
  env.any_of([mailbox.get(), env.timeout()]), discarding wrong codes in a
  loop with a shrinking deadline — the same approach as examples/lite/process_events.py.
'''
import simpy
from random import randint


class MyComponent:
    ''' This represents a coding machine.

    A lock consisiting of 4 times 2 digits numbers (codes) is provided.
    The codes are dynamically generated.

    An attacker has 4 * 10 millisecond to break all the codes.
    Every code break takes 10 millisecond max, otherwise new 4 codes
    are generated.
    If a code was guessed, attacker has to guess next code in 10
    milliseconds...

    Two different attackers are provided.
    '''

    def __init__(self, name, env):
        self.name = name
        self.env = env
        self.stat = {'timeout': 0, 'success': 0, 'tries': 0}
        # Shared mailbox: attackers put codes in, locker consumes them.
        self._mailbox = simpy.Store(env)
        env.process(self.locker_state_machine())

    def boot(self):
        self.env.process(self.attacker1())
        self.env.process(self.attacker2())

    def attacker1(self):
        ''' Attacker provides random numbers to try to break the locker machine '''
        while True:
            code = randint(0, 100), randint(0, 100)
            # SimPy has no direct process-to-process send.
            # The idiomatic way is to put the value into a shared Store.
            # The locker pulls from the Store whenever it is ready to receive.
            # DSSim equivalent: self.sim.signal(code, self.sm)
            self._mailbox.put(code)
            self.stat['tries'] += 1
            # 2 ms to generate the code, send it and check the status of unlock
            yield self.env.timeout(0.002)

    def attacker2(self):
        ''' Attacker tries to guess that the code once becomes 1-1-1-1 '''
        while True:
            # SimPy has no direct process-to-process send.
            # The idiomatic way is to put the value into a shared Store.
            # The locker pulls from the Store whenever it is ready to receive.
            # DSSim equivalent: self.sim.signal(1, self.sm)
            self._mailbox.put((1, 1))
            self.stat['tries'] += 1
            # 500 us to generate the code, send it and check the status of unlock
            yield self.env.timeout(0.0005)

    def _wait_for_code(self, timeout, expected):
        '''Wait up to *timeout* seconds for *expected* to arrive.

        Implements condition-filtered timeout wait using env.any_of().
        Wrong codes are discarded and the deadline shrinks across retries —
        the same semantics as DSSim's gwait(timeout, cond=lambda e: e == expected).

        Returns the matched code on success, or None on timeout.
        '''
        deadline = self.env.now + timeout
        while True:
            remaining = deadline - self.env.now
            if remaining <= 0:
                return None
            get_event = self._mailbox.get()
            timeout_event = self.env.timeout(remaining)
            yield self.env.any_of([get_event, timeout_event])
            if get_event.triggered:
                code = get_event.value
                if code == expected:
                    return code
                # Wrong code — discard and loop with remaining time
            else:
                # Timeout fired — remove the pending get from the store queue
                self._mailbox.get_queue.remove(get_event)
                return None

    def locker_state_machine(self):
        while True:
            lock_code = randint(0, 100), randint(0, 100)
            rv = yield from self._wait_for_code(0.01, lock_code)
            if rv is None:
                self.stat['timeout'] += 1
            else:
                self.stat['success'] += 1

if __name__ == '__main__':
    env = simpy.Environment()
    obj0 = MyComponent(name='obj0', env=env)
    obj0.boot()
    print('Running...')

    import cProfile
    cProfile.run('env.run(until=600)')  # run 10 minutes
    print('Done.')
    print(f'Successful attempts: {obj0.stat["success"]}')
    print(f'Timed out attempts: {obj0.stat["timeout"]}')
    print(f'Attempts: {obj0.stat["tries"]}')
    assert 20 <= obj0.stat["success"] <= 50  # high probability to pass
    assert obj0.stat["tries"] == 1500002
