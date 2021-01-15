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
LiteLayer2 counterpart of examples/pubsub/gasstation.py.
'''
from random import randint

from dssim import DSSimulation, DSLiteAgent, LiteLayer2

GAS_STATION_SIZE = 200.0
THRESHOLD = 25.0
FUEL_TANK_SIZE = 50.0
FUEL_TANK_LEVEL = (5, 25)
REFUELING_SPEED = 2.0
TANK_TRUCK_TIME = 300
T_INTER = (10, 100)
SIM_TIME = 30000


class Car(DSLiteAgent):
    def process(self):
        fuel_tank_level = randint(*FUEL_TANK_LEVEL)
        print(f'{sim.time} {self} waiting for a gas station...')
        yield from self.gget(gas_station)
        liters_required = FUEL_TANK_SIZE - fuel_tank_level
        print(f'{sim.time} {self} waiting for {liters_required} liters of fuel...')
        if (fuel_pump.amount - liters_required) / fuel_pump.capacity * 100 < THRESHOLD:
            print(f'{sim.time} {self} calling truck for the fuel...')
            TankTruck(sim=self.sim)
        print(f'{sim.time} {self} going to tank {liters_required} liters...')
        yield from self.gget_n(fuel_pump, liters_required)
        print(f'{sim.time} {self} starting to tank {liters_required} liters...')
        yield from self.gwait(int(liters_required / REFUELING_SPEED))
        print(f'{sim.time} {self} filled tanking of {liters_required} liters and leaving.')
        yield from self.gput(gas_station)


class TankTruck(DSLiteAgent):
    def process(self):
        print(f'{sim.time} {self} starting...')
        yield from self.gwait(TANK_TRUCK_TIME)
        amount = fuel_pump.capacity - fuel_pump.amount
        print(f'{sim.time} {self} at station, {fuel_pump.amount}/{fuel_pump.capacity} capacity, adding {amount} fuel...')
        yield from self.gput_n(fuel_pump, amount)
        print(f'{sim.time} {self} leaving station after {amount} of new fuel, filled to {fuel_pump.amount}.')


class CarGenerator(DSLiteAgent):
    def process(self):
        while True:
            yield from self.gwait(randint(*T_INTER))
            Car(sim=self.sim)


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    gas_station = sim.resource(2, name="Gas station places")
    fuel_pump = sim.resource(capacity=GAS_STATION_SIZE, name="Gas station fuel")
    TankTruck(sim=sim)
    CarGenerator(sim=sim)

    sim.run(SIM_TIME)
    assert sim.time > 29900
