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
LiteLayer2 adaptation of process_events.py.

Key differences from the PubSubLayer2 version:

* LiteLayer2 has no DSProcess / .signal() / cond-filtered gwait().
* The locker generator is stored as ``self._locker_gen`` and the attacker
  signals it via ``sim.signal(code, self._locker_gen)``.
* Condition filtering is done manually in ``_wait_for_code()``, which loops
  with a shrinking timeout until the right code arrives or the deadline passes.
'''
from dssim import DSComponent, DSSimulation
from dssim.simulation import LiteLayer2
from random import randint


class MyComponent(DSComponent):
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

    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self.stat = {'timeout': 0, 'success': 0, 'tries': 0}
        # Create the locker generator and keep a reference so the attacker
        # can address events directly to it via sim.signal().
        self._locker_gen = self.locker_state_machine()
        self.sm = self._locker_gen
        self.sim.schedule(0, self.sm)

    def boot(self):
        self.sim.schedule(0, self.attacker1())
        self.sim.schedule(0, self.attacker2())

    def attacker1(self):
        ''' Attacker provides random numbers to try to break the locker machine '''
        while True:
            code = randint(0, 100), randint(0, 100)
            # The following signals directly to the generator - this is allowed only if the
			# target generator does not signal anything back
			# However the always safe way to do this:
            # self.sim.signal(code, self.sm)
            self.sim.send_object(self._locker_gen, code)  # send directly event "code"
            self.stat['tries'] += 1
            # 2 ms to generate the code, send it and check the status of unlock
            yield from self.sim.gwait(0.002)

    def attacker2(self):
        ''' Attacker tries to guess that the code once becomes 1-1-1 '''
        while True:
            # The following signals directly to the process - this is allowed only if the
			# target process does not signal anything back
			# However the always safe way to do this:
            # self.sim.signal(1, self.sm)
            self.sim.send_object(self._locker_gen, (1, 1))  # send directly event "1"
            self.stat['tries'] += 1
            # 500 us to generate the code, send it and check the status of unlock
            yield from self.sim.gwait(0.0005)

    def _wait_for_code(self, timeout, expected):
        '''Wait up to *timeout* seconds for *expected* to arrive.

        Unlike PubSubLayer2's ``gwait(cond=...)``, LiteLayer2's ``gwait()``
        accepts one event per yield.  This helper loops with the remaining
        time budget so that wrong codes are discarded and the deadline is
        respected across multiple receives.

        Returns ``True`` when the expected code arrives within the deadline,
        ``False`` on timeout.
        '''
        deadline = self.sim._simtime + timeout
        while True:
            remaining = deadline - self.sim.time
            if remaining <= 0:
                return None
            rv = yield from self.sim.gwait(remaining)
            if rv == expected or rv is None:
                return rv


    def locker_state_machine(self):
        while True:
            lock_code = randint(0, 100), randint(0, 100)
            rv = yield from self._wait_for_code(0.01, lock_code)
            if rv is None:
                self.stat['timeout'] += 1
            else:
                self.stat['success'] += 1

if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    obj0 = MyComponent(name='obj0', sim=sim)
    obj0.boot()
    print('Running...')

    import cProfile
    cProfile.run('sim.run(600)') # run 10 minutes
    print('Done.')
    print(f'Successful attempts: {obj0.stat["success"]}')
    print(f'Timed out attempts: {obj0.stat["timeout"]}')
    print(f'Attempts: {obj0.stat["tries"]}')
    print(f'Simulation events: {sim.num_events}')
    assert 20 <= obj0.stat["success"] <= 50  # high probability to pass
    assert obj0.stat["tries"] == 1500002
    assert 1550000 <= sim.num_events <= 1560000  # high probability to pass
