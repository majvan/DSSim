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
from dssim.simulation import DSComponent, DSProcess, DSSimulation
from dssim.pubsub import DSProducer
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
        self.stat = {'errors': 0, 'success': 0, 'tries': 0}
        self.sm = DSProcess(self.locker_state_machine(), name=self.name+'.rx_sm', sim=self.sim).schedule(0)

    def boot(self):
        DSProcess(obj0.attacker1(), name=self.name+'.attacker', sim=self.sim).schedule(0)

    def attacker1(self):
        ''' Attacker provides random numbers to try to break the locker machine '''
        while True:
            code = randint(0, 100)
            self.sm.signal(code)
            self.stat['tries'] += 1
            # 2 ms to generate the code, send it and check the status of unlock
            yield from self.sim.wait(0.002)

    def attacker2(self):
        ''' Attacker tries to guess that the code once becomes 1-1-1-1 '''
        while True:
            self.sm.signal(1)
            self.stat['tries'] += 1
            # 500 us to generate the code, send it and check the status of unlock
            yield from self.sim.wait(0.0005)

    def locker_state_machine(self):
        while True:
            lock_code = [randint(0, 100), randint(0, 100), randint(0, 100), randint(0, 100)]
            while True:
                rv = yield from self.sim.wait(0.01, cond=lambda e: e == lock_code[0])
                if rv is None:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e == lock_code[1])
                if rv is None:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e == lock_code[2])
                if rv is None:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e == lock_code[3])
                if rv is None:
                    break
                self.stat['success'] += 1
            # Locker closed, the number was not guessed
            self.stat['errors'] += 1

if __name__ == '__main__':
    sim = DSSimulation()
    obj0 = MyComponent(name='obj0', sim=sim)
    obj0.boot()
    print('Running...')

    import cProfile
    cProfile.run('sim.run(3600)')
    print('Done.')
    print(f'Successful attempts: {obj0.stat["success"]}')
    print(f'Unsuccessful attempts: {obj0.stat["errors"]}')
    print(f'Attempts: {obj0.stat["tries"]}')
    print(f'Simulation events: {sim.num_events}')
    assert obj0.stat["success"] <= 5  # high probability to pass
    assert obj0.stat["tries"] == 1800001
    # assert sim.num_events == obj0.stat["tries"] + obj0.stat["errors"] + 1
    assert 3948000 <= sim.num_events <= 3952000  # high probability to pass

