from dssim import DSProcessComponent, PCGenerator, Queue, DSSimulation
import random
sim = DSSimulation()

class Product(DSProcessComponent):
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

c0 = Queue(1)
i0 = Queue(1)
c1 = Queue(1)
gen = PCGenerator(Product, lambda p: random.uniform(5, 15))
time, ev = sim.run(150)
assert 135 < time <= 150, f"Unexpected value of the time of last event the simulation: {time}"
assert 125 < ev <= 155, f"Unexpected number of events: {ev}"

