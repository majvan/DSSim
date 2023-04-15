from dssim import DSSimulation, DSProcessComponent, Resource
from random import randint

GAS_STATION_SIZE = 200.0  # liters
THRESHOLD = 25.0  # Threshold for calling the tank truck (in %)
FUEL_TANK_SIZE = 50.0  # liters
# Min/max levels of fuel tanks (in liters)
FUEL_TANK_LEVEL = (5, 25)
REFUELING_SPEED = 2.0  # liters / second
TANK_TRUCK_TIME = 300  # Seconds it takes the tank truck to arrive
T_INTER = (10, 100)  # Create a car every [min, max] seconds
SIM_TIME = 30000  # Simulation time in seconds

class Car(DSProcessComponent):
    """
    A car arrives at the gas station for refueling.

    It requests one of the gas station's fuel pumps and tries to get the
    desired amount of gas from it. If the stations reservoir is
    depleted, the car has to wait for the tank truck to arrive.

    """

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
        yield from self.gget(fuel_pump, liters_required)
        print(f'{sim.time} {self} starting to tank {liters_required} liters...')
        yield from self.sim.gwait(int(liters_required / REFUELING_SPEED)) # int is not needed
        print(f'{sim.time} {self} filled tanking of {liters_required} liters and leaving.')
        yield from self.gput(gas_station)


class TankTruck(DSProcessComponent):
    def process(self):
        print(f'{sim.time} {self} starting...')
        yield from self.sim.gwait(TANK_TRUCK_TIME)
        amount = fuel_pump.capacity - fuel_pump.amount
        print(f'{sim.time} {self} at station, {fuel_pump.amount}/{fuel_pump.capacity} capacity, adding {amount} fuel...')
        yield from self.gput(fuel_pump, amount)
        print(f'{sim.time} {self} leaving station after {amount} of new fuel, filled to {fuel_pump.amount}.')
        

class CarGenerator(DSProcessComponent):
    """
    Generate new cars that arrive at the gas station.
    """

    def process(self):
        while True:
            yield from self.sim.gwait(randint(*T_INTER))
            Car(sim=self.sim)

if __name__ == '__main__':
    # Create environment and start processes
    sim = DSSimulation()
    gas_station = Resource(2, name="Gas station places", sim=sim)  # 2 places in gas station
    fuel_pump = Resource(capacity=GAS_STATION_SIZE, name="Gas station fuel", sim=sim)
    tank_truck = TankTruck(sim=sim)
    CarGenerator(sim=sim)

    sim.run(SIM_TIME)
    print("Done.")
    assert sim.time > 29900
