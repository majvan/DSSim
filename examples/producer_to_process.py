from dssim import DSSimulation, DSProcess, DSComponent, DSCallback, Timer

class MyComponent(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        prod = Timer(name=self.name+'.timer', period=1).start().tx

        # The following shows 3 independent producer-to-process connections.
        # They run in parallel - feel free to comment out not interesting ones to see the behavior

        # Case 1: The producer event starts a new process 'start_process'
        starter = lambda e: DSProcess(self.start_process(e)).schedule(0)  # the starter is a new function which schedules a new process
        prod.add_subscriber(DSCallback(starter), phase='pre')

        # Case 2: The producer event pushes events into running 'listen_process'
        proc = DSProcess(self.listen_process(), name=self.name+'.listener').schedule(0)
        prod.add_subscriber(proc, phase='pre')

        # Case 3: The producer event starts a new process 'start_listen_process' and then pushes events to it
        starter = lambda e: \
            prod.add_subscriber(
                DSProcess(self.start_listen_process(e)).schedule(0),  # this creates a new process
                phase='pre')  # and connects the new process with the producer
        prod.add_subscriber(DSCallback(starter), phase='pre')

    async def start_process(self, arg_event):
        print(self.sim.time, f"start_process({arg_event}) started.")
        assert arg_event['tick'] == self.sim.time
        for i in range(10):
            event = await self.sim.wait(cond=lambda e:True)  # wait for any event
            assert False, 'This process never gets signaled, because it is not subscribed to any producer'

    async def listen_process(self):
        print(self.sim.time, "listen_process() started.")
        for i in range(10):
            event = await self.sim.wait(cond=lambda e:True)  # wait for any event
            print(self.sim.time, "listen_process() signaled with", event)
            assert event['tick'] == self.sim.time == i + 1

    async def start_listen_process(self, arg_event):
        print(self.sim.time, f"start_listen_process({arg_event}) started.")
        assert arg_event['tick'] == self.sim.time
        for i in range(10):
            event = await self.sim.wait(cond=lambda e:True)  # wait for any event
            print(self.sim.time, f"start_listen_process({arg_event}) signaled with", event)
            assert event['tick'] == self.sim.time == i + arg_event['tick'] + 1

  
sim = DSSimulation()
mc = MyComponent()
sim.run(20)