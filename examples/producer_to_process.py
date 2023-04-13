from dssim.simulation import DSSimulation, DSProcess, DSComponent, DSCallback
from dssim.components.clock import Timer

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        prod = Timer(name=self.name+'.timer', period=1).start().tx

        starter = lambda e: DSProcess(self.start_process(e)).schedule(0)
        prod.add_subscriber(DSCallback(starter, name=self.name+'.starter'), phase='pre')
        proc = DSProcess(self.listen_process(), name=self.name+'.listener').schedule(0)
        prod.add_subscriber(proc, phase='pre')

    async def start_process(self, *args, **kwargs):
        print(self.sim.time, "start_process() started with", args, kwargs)
        event = args[0]
        assert event['tick'] == self.sim.time
        for i in range(1000):
            event = await self.sim.wait(cond=lambda e:True)  # wait for any event
            assert False, 'This process never gets signaled, because it is not subscribed to any producer'

    async def listen_process(self, *args, **kwargs):
        print(self.sim.time, "listen_process() started with", args, kwargs)
        for i in range(1000):
            event = await self.sim.wait(cond=lambda e:True)  # wait for any event
            print(self.sim.time, "listen_process() signaled with", event)
            assert event['tick'] == self.sim.time

  
sim = DSSimulation()
mc = MyComponent()

sim.run(100)