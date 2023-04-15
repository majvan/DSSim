# demo wait.py
"""
Here, princes, are generated.
In the meantime, kings die.
The youngest prince, will become king.

If a new prince arrives, he checks, whether there's a king.
If so, he will wait for a kingdied trigger.
If not, he will become king.

Note that in this demo, the priority (-now) in wait is used to make
the youngest prince to become king.

This is demo of the trigger/waitfor mechanism,
just to allow one waiter to be honored.
"""
from dssim import DSSimulation, DSAbsTime as _abs, Mutex, DSProcessComponent
import random


class PrinceGenerator(DSProcessComponent):
    async def process(self):
        while True:
            await self.sim.wait(int(random.expovariate(1/20)))  # every 10-20 years othere's a new heir of the throne
            Prince()


class Prince(DSProcessComponent):
    async def process(self):
        global kingdom, kings, lastkingdied
        self.live_till = self.sim.time + random.randint(60, 90)
        print(self.sim.time, self, "going to live till", self.live_till)
        if not kingdom.locked():  # there is no king, so this prince will become king, immediately
            kings.append(("no king", lastkingdied, self.sim.time, self.sim.time - lastkingdied))
        async with kingdom.open(_abs(self.live_till)) as event:  # The mutex will be released automatically after closing block.
            if not event:  # timeout returns None event
                print(self.sim.time, self, "dies before getting to the throne")
                return
            print(self.sim.time, self, "Vive le roi!")
            kings.append((self.name, self.sim.time, self.live_till, self.live_till - self.sim.time))
            await self.sim.wait(_abs(self.live_till))
            lastkingdied = self.sim.time
            print(self.sim.time, self, "Le roi est mort.")


sim = DSSimulation()
lastkingdied = sim.time
kings = []
kingdom = Mutex(name='kingdom')  # we do not need State for this, all we need is simple notification routing
PrinceGenerator()

sim.run(5000)
print("king                     from       to duration")
for king in kings:
    print("{:20}{:9d}{:9d}{:9d}".format(*king))
