# Copyright 2026- majvan (majvan@gmail.com)
"""
Pandemia
"""

from dssim import DSComponent, DSSimulation

from population import (
    Population,
    InfectedPopulation,
    ImmunePopulation,
    DiagnosedPopulation,
    RecoveredPopulation,
    DeadPopulation,
)


class GenericPopulation(DSComponent):
    """A generic population with different components."""

    def __init__(self, csv, **kwargs):
        super().__init__(**kwargs)
        self.csv = csv

        self.generic = [Population(5e6, name=self.name + '.unaffected', sim=self.sim)]
        self.infected = [InfectedPopulation(1, name=self.name + '.infected', sim=self.sim)]
        self.diagnosed = []
        self.recovered = []
        self.dead = [DeadPopulation(0, name=self.name + '.dead', sim=self.sim)]
        self.immune = [ImmunePopulation(0e6, name=self.name + '.immune', sim=self.sim)]

        self.people_container = [self.generic, self.infected, self.diagnosed, self.recovered, self.immune]

        # Concentrate all infection/population events here and fan out.
        self.infection_rx = self.sim.kw_callback(self.infection_distributor, name=self.name + '.infection rx')
        self.population_rx = self.sim.kw_callback(self.population_distributor, name=self.name + '.population rx')

        self.sim.process(self.time_observer(), name=self.name + '.time observer').schedule(0)

        for group in self.people_container:
            for pop in group:
                pop.infection_tx.add_subscriber(self.infection_rx)
                pop.population_tx.add_subscriber(self.population_rx)

        self._bucket_ids = {'infected': 0, 'recovered': 0, 'diagnosed': 0}

    def _get_group_population(self, *groups):
        total = 0
        for grp in groups:
            total += sum(p.population for p in grp)
        return total

    def _next_bucket_name(self, prefix):
        self._bucket_ids[prefix] += 1
        return f'{self.name}.{prefix}.{self._bucket_ids[prefix]}'

    def infection_distributor(self, population, infection, **kwargs):
        # Resend to all groups proportionally to each group's size.
        if not infection:
            return

        size = self._get_group_population(*self.people_container)
        if size <= 0:
            return

        for group in self.people_container:
            for pop in group:
                eff_infection = population * infection
                eff_population = eff_infection * pop.population / size
                pop.accept_infection(population=eff_population, **kwargs)

    def population_distributor(self, source, new_infected=0, new_dead=0, new_recovered=0, new_diagnosed=0, **kwargs):
        if new_infected:
            new_pop = InfectedPopulation(new_infected, name=self._next_bucket_name('infected'), sim=self.sim)
            new_pop.infection_tx.add_subscriber(self.infection_rx)
            new_pop.population_tx.add_subscriber(self.population_rx)
            self.infected.append(new_pop)

        if new_dead:
            self.dead[0].update_population(new_dead)

        if new_recovered:
            day = kwargs['day_after_infected']
            for pop in self.recovered:
                if day == pop.get_day():
                    pop.update_population(new_recovered)
                    break
            else:
                new_pop = RecoveredPopulation(new_recovered, name=self._next_bucket_name('recovered'), sim=self.sim)
                new_pop.infection_tx.add_subscriber(self.infection_rx)
                new_pop.population_tx.add_subscriber(self.population_rx)
                self.recovered.append(new_pop)

        if new_diagnosed:
            day = kwargs['day_after_infected']
            for pop in self.diagnosed:
                if day == pop.get_day():
                    pop.update_population(new_diagnosed)
                    break
            else:
                new_pop = DiagnosedPopulation(new_diagnosed, name=self._next_bucket_name('diagnosed'), sim=self.sim)
                new_pop.infection_tx.add_subscriber(self.infection_rx)
                new_pop.population_tx.add_subscriber(self.population_rx)
                self.diagnosed.append(new_pop)

    async def time_observer(self):
        day = -1
        await self.sim.wait(0.8)
        while True:
            await self.sim.wait(1)
            day += 1

            total = self._get_group_population(*self.people_container, self.dead)
            generic = self._get_group_population(self.generic)
            total_infected = self._get_group_population(self.infected, self.diagnosed)
            infected = self._get_group_population(self.infected)
            diagnosed = self._get_group_population(self.diagnosed)
            recovered = self._get_group_population(self.recovered)
            immune = self._get_group_population(self.immune)
            dead = self._get_group_population(self.dead)

            if self.csv is not None:
                self.csv.write(
                    f'{day},{total},{generic},{total_infected},{infected},{diagnosed},{recovered},{immune},{dead}\n'
                )

            print(
                'Day:{}  Total:{}  Generic:{}  Total infected:{}  Infected:{}  Diagnosed:{}  Recovered:{}  Immune:{}  Dead:{}'.format(
                    day,
                    total,
                    generic,
                    total_infected,
                    infected,
                    diagnosed,
                    recovered,
                    immune,
                    dead,
                )
            )


if __name__ == '__main__':
    sim = DSSimulation()
    with open('result.csv', 'w') as f:
        f.write('Day,Total,Unaffected,Total infected,Infected,Diagnosed,Recovered,Immune,Dead\n')
        GenericPopulation(name='Generic', csv=f, sim=sim)
        sim.run(365)
    print(sim.time)
