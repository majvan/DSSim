# Copyright 2026- majvan (majvan@gmail.com)
from dssim import DSAgent, PCGenerator, DSSimulation
import random
sim = DSSimulation()

class Product(DSAgent):
    async def process(self):
        await self.enter(c0)
        await sim.wait(3)
        self.leave(c0)
        await self.enter(i0)
        await sim.wait(15)
        self.leave(i0)
        await self.enter(c1)
        await sim.wait(3)
        self.leave(c1)

c0 = sim.queue(1)
i0 = sim.queue(1)
c1 = sim.queue(1)
gen = PCGenerator(Product, lambda p: random.uniform(5, 15))
time, ev = sim.run(150)
assert 135 < time <= 150, f"Unexpected value of the time of last event the simulation: {time}"
assert 74 < ev <= 90, f"Unexpected number of events: {ev}"
