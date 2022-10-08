"""
Pandemia
"""
from dssim.simulation import sim, DSComponent, DSSchedulable
from dssim.pubsub import DSProcessConsumer, DSConsumer, DSProducer

class Population(DSComponent):
    """A generic pandemic process on a population """
    def __init__(self, population, **kwargs):
        super().__init__(**kwargs)
        self.population = population
        self.new_infected = 0
        self.new_diagnosed = 0
        self.new_dead = 0
        self.new_recovered = 0
        self.new_population = 0
        self.day = 0

        self.step = 0

        self.infection_tx = DSProducer(name=self.name + ".infection tx")
        self.population_tx = DSProducer(name=self.name + ".population tx")
        self.status_tx = DSProducer(name=self.name + ".status tx")
        delay = 1 + int(sim.time) - sim.time
        sim.schedule(delay, self.process())  # schedule at the beginning of time

    def update_population(self, delta):
        # Accept newcomers to population in 0.7
        if delta > 0:
            self.population += delta
        else:
            self.population = max(0, self.population + delta)

    def accept_infection(self, population, **kwargs):
        # compute what is the share of our population compared with the accepted population
        if 'unaffected' in self.name and self.step > 360:
            pass
        self.new_infected += population * self.infection_reception_ratio

    def accept_diagnostic(self, tested_ratio, **kwargs):
        self.new_diagnosed += (self.population - self.new_diagnosed) * self.diagnose_ratio * tested_ratio

    def get_day(self):
        return self.day

    def make_step(self):
        self.step += 1
        """ Standard population procedure

        1. Transmit infection to the parent_population (time = 0.2)
        2. Receive new_infected from parent_population by the handler accept_infection (time = 0.2)
        3. From the new_infected, compute new population movement (time = 0.5)
        4. Transmit changes in the population to the parent_population (time = 0.7)
        5. Receive new population from parent_population by the handler update_population (time = 0.7)
        """
        yield from self.sim.wait(0.2)

        # Infect population in time 0.2
        self.infection_tx.signal(source=self, population=self.population, infection=self.infection_rate)
        yield from self.sim.wait(0.3)

        # Re-populate the population in time 0.5
        population = self.population
        # self-diagnosis by symptomps
        self.accept_diagnostic(self.tested_ratio)
        self.new_diagnosed = min(self.population, self.new_diagnosed)
        new_state = int(self.new_diagnosed)
        if new_state >= 1:
            self.population_tx.schedule(0.2, source=self, new_diagnosed=new_state, day_after_infected=self.day)
            self.population -= new_state
        self.new_diagnosed -= new_state

        # and infect those which are not yet
        self.new_infected = min(self.population, self.new_infected)
        new_state = int(self.new_infected)
        if new_state >= 1:
            self.population_tx.schedule(0.2, source=self, new_infected=new_state)
            self.population -= new_state
        self.new_infected -= new_state

        self.new_dead += population * self.dead_ratio
        self.new_dead = min(self.population, self.new_dead)
        new_state = int(self.new_dead)
        if new_state >= 1:
            self.population_tx.schedule(0.2, source=self, new_dead=new_state, day_after_infected=self.day)
            self.population -= new_state
        self.new_dead -= new_state

        self.new_recovered += population * self.recovery_ratio
        self.new_recovered = min(self.population, self.new_recovered)
        new_state = int(self.new_recovered)
        if new_state >= 1:
            self.population_tx.schedule(0.2, source=self, new_recovered=new_state, day_after_infected=self.day)
            self.population -= new_state
        self.new_recovered -= new_state
        yield from self.sim.wait(0.5)

    def process(self):
        self.infection_reception_ratio = 1
        self.infection_rate = 0
        self.diagnose_ratio = 0 # from healthy population, no diagnose
        self.tested_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0
        while True:
            yield from self.make_step()

class InfectedPopulation(Population):
    """A simple pandemic infected population """
    def __init__(self, population, **kwargs):
        super().__init__(population, **kwargs)

        self.infection_tx = DSProducer(name=self.name+".infection tx")
        self.population_tx = DSProducer(name=self.name+".population tx")
        self.status_tx = DSProducer(name=self.name+".status tx")
        self.infection_rx = DSConsumer(self.accept_infection, name=self.name+".infection rx")

    def accept_infection(self, population, **kwargs):
        pass  # we are already infected

    def process(self):
        # Virus incubation
        self.infection_reception_ratio = 0
        self.infection_rate = 1
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0
        while True:
            yield from self.make_step()

class DeadPopulation(Population):
    """A simple pandemic process on a population """

    def accept_infection(self, population, **kwargs):
        pass # we are already infected

    def accept_diagnostic(self, tested_ratio, **kwargs):
        pass  # we are diagnosed

    @DSSchedulable
    def process(self):
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0

class DiagnosedPopulation(InfectedPopulation):
    """A diagnosed when put into """
    def accept_diagnostic(self, tested_ratio, **kwargs):
        pass

class RecoveredPopulation(Population):
    """A diagnosed when put into """
    def accept_diagnostic(self, tested_ratio, **kwargs):
        pass

    @DSSchedulable
    def process(self):
        # Virus incubation
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0

class ImmunePopulation(Population):
    """An immmune population """
    def accept_infection(self, population, **kwargs):
        pass  # we will never get infected

    def accept_diagnostic(self, tested_ratio, **kwargs):
        pass

    @DSSchedulable
    def process(self):
        # Virus incubation
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.infection_rate = 0
