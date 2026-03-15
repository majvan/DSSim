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

c0 = sim.queue(1, name='c0')
i0 = sim.queue(1, name='i0')
c1 = sim.queue(1, name='c1')
c0_probe = c0.add_stats_probe(name='users')
i0_probe = i0.add_stats_probe(name='users')
c1_probe = c1.add_stats_probe(name='users')
gen = PCGenerator(Product, lambda p: random.uniform(5, 15))
time, ev = sim.run(150)
for probe in (c0_probe, i0_probe, c1_probe):
    stats = probe.get_statistics()
    print(
        f'Summary: {probe.name} '
        f'avg_len={stats["time_avg_len"]:.3f}, '
        f'max_len={stats["max_len"]}, '
        f'nonempty_ratio={stats["time_nonempty_ratio"]:.3f}, '
        f'puts={stats["put_count"]}, '
        f'gets={stats["get_count"]}'
    )
assert 135 < time <= 150, f"Unexpected value of the time of last event the simulation: {time}"
# DSQueue probe callbacks add observer work, so total event count is higher than the uninstrumented variant.
assert 120 < ev <= 160, f"Unexpected number of events: {ev}"
