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
from dssim.simulation import DSComponent, sim
from dssim.pubsub import DSProducer, DSProcessConsumer
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
        self.sm = DSProcessConsumer(self.locker_state_machine(), start=True, name=self.name+'.rx_sm')

    def boot(self):
        self.sim.schedule(0, obj0.attacker1())

    def attacker1(self):
        ''' Attacker provides random numbers to try to break the locker machine '''
        while True:
            code = randint(0, 100)
            self.sm.notify(code=code)
            self.stat['tries'] += 1
            # 2 ms to generate the code, send it and check the status of unlock
            yield from self.sim.wait(0.002)

    def attacker2(self):
        ''' Attacker can provide only constant code 1-1-1-1 '''
        while True:
            sim.signal(self.sm, code=1)
            self.stat['tries'] += 1
            # 500 us to generate the code, send it and check the status of unlock
            yield from self.sim.wait(0.0005)

    def locker_state_machine(self):
        while True:
            lock_code = [randint(0, 100), randint(0, 100), randint(0, 100), randint(0, 100)]
            while True:
                rv = yield from self.sim.wait(0.01, cond=lambda e: e['code'] == lock_code[0])
                if not rv:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e['code'] == lock_code[1])
                if not rv:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e['code'] == lock_code[2])
                if not rv:
                    break
                rv = yield from self.sim.wait(0.01, cond=lambda e: e['code'] == lock_code[3])
                if not rv:
                    break
                self.stat['success'] += 1
            # Locker closed, the number was not guessed
            self.stat['errors'] += 1

if __name__ == '__main__':
    obj0 = MyComponent(name='obj0')
    obj0.boot()
    print('Running...')
    sim.run(3600)
    print('Done.')
    print(obj0.stat['success'])
    print(obj0.stat['errors'])
    print(obj0.stat['tries'])
