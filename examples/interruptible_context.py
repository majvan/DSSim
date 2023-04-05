from dssim.simulation import DSSimulation, DSComponent, DSProcess
from dssim.pubsub import DSProducer, DSTransformation

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ep = DSProducer(name=self.name + '.ep', sim=self.sim)

    async def process0(self):
        ''' The process listens on the self.ep producer in a way that all the events
        from the producer are transformed to the ValueError(e).
        The exception interrupts the context.
        '''
        try:
            ep = DSTransformation(self.ep, lambda e: ValueError(e))
            with self.sim.observe_pre(ep) as cm:
                print(self.sim.time, 'Waiting...')
                event = await self.sim.wait(100)  # No signal should stop this, only Exception
                assert False, 'This should not be executed because a signal from main creates exception'
        except Exception as e:
            print(self.sim.time, 'Interrupted.')
            assert self.sim.time == 10
            assert isinstance(e, ValueError)
            assert str(e) == 'Hello'
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert sum(ep.subs['pre'].d.values()) == 0

    async def process1(self):
        ''' The process listens on the process endpoint and transfers 
        from the producer are transformed to the ValueError(e).
        The exception interrupts the context.
        '''
        try:
            ep = DSTransformation(self.ep, lambda e: ValueError(e + ' catched'))
            with self.sim.interruptible(10, cond='Hi!'):
                with self.sim.observe_pre(ep) as cm:
                    print(self.sim.time, 'Waiting 100')
                    event = await self.sim.wait(100)  # No signal should stop this, only Exception
                assert False, 'This should not be executed because a signal from main creates exception'
        except Exception as e:
            print(self.sim.time, e)
        assert sum(self.ep.subs['pre'].d.values()) == 0
        assert sum(ep.subs['pre'].d.values()) == 0


async def main(mc):
    sim.schedule(0, mc.process0())
    await sim.wait(10)
    mc.ep.signal('Hello')
    # TODO: implement interruptible
    
sim = DSSimulation()
mc = MyComponent(sim=sim)
sim.schedule(0, main(mc))
sim.run()
