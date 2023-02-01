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
from dssim.simulation import DSSimulation, DSAbsTime as _abs
from dssim.pubsub import DSProducer
from dssim.processcomponent import DSProcessComponent
import random


class PrinceGenerator(DSProcessComponent):
    def process(self):
        while True:
            yield from self.sim.wait(int(random.expovariate(1/20)))  # every 10-20 years othere's a new heir of the throne
            Prince()


class Prince(DSProcessComponent):
    def process(self):
        global king, kings, lastkingdied
        self.live_till = self.sim.time + random.randint(60, 90)
        print(self.sim.time, self, "going to live till", self.live_till)
        if king is None:  # there is no king, so this prince will become king, immediately
            kings.append(("no king", lastkingdied, self.sim.time, self.sim.time - lastkingdied))
        with self.sim.consume(king_died):  # with consume we manage that once we get notified, we consume event and noone else gets notified
            event = yield from self.sim.check_and_wait(_abs(self.live_till), cond=lambda e: True)  # any message will interrupt, because only king died messages are sent here
            if not event:  # timeout returns None event
                print(self.sim.time, self, "dies before getting to the throne")
                return
        king = self
        print(self.sim.time, self, "Vive le roi!")
        kings.append((self.name, self.sim.time, self.live_till, self.live_till - self.sim.time))
        yield from self.sim.wait(_abs(self.live_till))
        king, lastkingdied = None, self.sim.time
        print(self.sim.time, self, "Le roi est mort.")
        king_died.signal('king died')


sim = DSSimulation()
king = None
lastkingdied = sim.time
kings = []
king_died = DSProducer(name='king died')  # we do not need State for this, all we need is simple notification routing
PrinceGenerator()

sim.run(5000)
print("king                     from       to duration")
for king in kings:
    print("{:20}{:9d}{:9d}{:9d}".format(*king))
