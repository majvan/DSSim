# Copyright 2026- majvan (majvan@gmail.com)
"""
Pandemia populations (ported to current DSSim pubsub stack).
"""

from dssim import DSComponent


class Population(DSComponent):
    """A generic pandemic process on a population."""

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

        self.infection_tx = self.sim.publisher(name=self.name + '.infection tx')
        self.population_tx = self.sim.publisher(name=self.name + '.population tx')
        self.status_tx = self.sim.publisher(name=self.name + '.status tx')

        delay = 1 + int(self.sim.time) - self.sim.time
        self.sim.process(self.process(), name=self.name + '.process').schedule(delay)

    def update_population(self, delta):
        if delta > 0:
            self.population += delta
        else:
            self.population = max(0, self.population + delta)

    def accept_infection(self, population, **kwargs):
        self.new_infected += population * self.infection_reception_ratio

    def accept_diagnostic(self, tested_ratio, **kwargs):
        self.new_diagnosed += (self.population - self.new_diagnosed) * self.diagnose_ratio * tested_ratio

    def get_day(self):
        return self.day

    async def make_step(self):
        self.step += 1
        await self.sim.wait(0.2)

        # Infect population in time 0.2
        self.infection_tx.signal_kw(source=self, population=self.population, infection=self.infection_rate)
        await self.sim.wait(0.3)

        # Re-populate the population in time 0.5
        population = self.population

        # Self-diagnosis by symptoms.
        self.accept_diagnostic(self.tested_ratio)
        self.new_diagnosed = min(self.population, self.new_diagnosed)
        new_state = int(self.new_diagnosed)
        if new_state >= 1:
            self.population_tx.schedule_kw_event(
                0.2,
                source=self,
                new_diagnosed=new_state,
                day_after_infected=self.day,
            )
            self.population -= new_state
        self.new_diagnosed -= new_state

        self.new_infected = min(self.population, self.new_infected)
        new_state = int(self.new_infected)
        if new_state >= 1:
            self.population_tx.schedule_kw_event(0.2, source=self, new_infected=new_state)
            self.population -= new_state
        self.new_infected -= new_state

        self.new_dead += population * self.dead_ratio
        self.new_dead = min(self.population, self.new_dead)
        new_state = int(self.new_dead)
        if new_state >= 1:
            self.population_tx.schedule_kw_event(
                0.2,
                source=self,
                new_dead=new_state,
                day_after_infected=self.day,
            )
            self.population -= new_state
        self.new_dead -= new_state

        self.new_recovered += population * self.recovery_ratio
        self.new_recovered = min(self.population, self.new_recovered)
        new_state = int(self.new_recovered)
        if new_state >= 1:
            self.population_tx.schedule_kw_event(
                0.2,
                source=self,
                new_recovered=new_state,
                day_after_infected=self.day,
            )
            self.population -= new_state
        self.new_recovered -= new_state
        await self.sim.wait(0.5)

    async def process(self):
        self.infection_reception_ratio = 1
        self.infection_rate = 0
        self.diagnose_ratio = 0  # from healthy population, no diagnose
        self.tested_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0
        while True:
            await self.make_step()


class InfectedPopulation(Population):
    """A simple pandemic infected population."""

    def __init__(self, population, **kwargs):
        super().__init__(population, **kwargs)
        self.infection_rx = self.sim.kw_callback(self.accept_infection, name=self.name + '.infection rx')

    def accept_infection(self, population, **kwargs):
        # Already infected.
        return None

    async def process(self):
        self.infection_reception_ratio = 0
        self.infection_rate = 1
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0
        while True:
            await self.make_step()


class DeadPopulation(Population):
    """Dead population bucket."""

    def accept_infection(self, population, **kwargs):
        return None

    def accept_diagnostic(self, tested_ratio, **kwargs):
        return None

    async def process(self):
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0


class DiagnosedPopulation(InfectedPopulation):
    """Diagnosed infected population bucket."""

    def accept_diagnostic(self, tested_ratio, **kwargs):
        return None


class RecoveredPopulation(Population):
    """Recovered population bucket."""

    def accept_diagnostic(self, tested_ratio, **kwargs):
        return None

    async def process(self):
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.recovery_ratio = 0


class ImmunePopulation(Population):
    """Immune population bucket."""

    def accept_infection(self, population, **kwargs):
        return None

    def accept_diagnostic(self, tested_ratio, **kwargs):
        return None

    async def process(self):
        self.infection_reception_ratio = 0
        self.infection_rate = 0
        self.tested_ratio = 0
        self.diagnose_ratio = 0
        self.dead_ratio = 0
        self.infection_rate = 0
