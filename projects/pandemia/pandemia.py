"""
Pandemia
"""
from dssim.simulation import sim, DSComponent
from dssim.pubsub import DSConsumer, DSProducer, DSProcessConsumer
from population import Population, InfectedPopulation, ImmunePopulation, DiagnosedPopulation, RecoveredPopulation, DeadPopulation

class GenericPopulation(DSComponent):
    """A generic population with different components """
    def __init__(self, csv, **kwargs):
        super().__init__(**kwargs)
        self.csv = csv

        self.generic = [Population(5e6, name=self.name + '.unaffected')]
        self.infected = [InfectedPopulation(1, name=self.name + '.infected')]
        self.diagnosed = []
        self.recovered = []
        self.dead = [DeadPopulation(0, name=self.name + '.dead')]
        self.immune = [ImmunePopulation(0e6, name=self.name + '.immune')]

        self.people_container = [self.generic, self.infected, self.diagnosed, self.recovered, self.immune]

        # These 2 endpoints will concentrate all the info about infection and spread it next
        self.infection_rx = DSConsumer(self.infection_distributor, name=self.name + '.infection rx')
        self.population_rx = DSConsumer(self.population_distributor, name=self.name + '.population rx')

        self.time_rx = DSProcessConsumer(self.time_observer(), start=True, name=self.name + '.time observer')

        for group in self.people_container:
            for pop in group:
                pop.infection_tx.add_consumer(self.infection_rx)

        for group in self.people_container:
            for pop in group:
                pop.population_tx.add_consumer(self.population_rx)

    def infection_distributor(self, population, infection, **kwargs):
        # just resend to all others, but with bare in mind the total population
        if infection:  # To reduce computation if infection is 0
            size = self._get_group_population(*self.people_container)
            # here is the idea: a group with size 'population' and infection rate (i.e. 3 met people during a day)
            # all we have to compute is how many of the met people are possibly the people met from particular group
            # so how many of other population it can infect
            for group in self.people_container:
                for pop in group:
                    eff_infection = population * infection  # how many from population will be infecting
                    eff_population = eff_infection * pop.population / size  # when infecting, how much will be affecting this population
                    pop.accept_infection(population=eff_population, **kwargs)

    def population_distributor(self, source, new_infected=0, new_dead=0, new_recovered=0, new_diagnosed=0, **kwargs):
        if new_infected:
            # print('Adding', new_infected, 'infected from', source.name)
            if False: # for pop in self.infected:
                if day == pop.get_day():
                    pop.update_population(new_infected)
                    break
            else:
                new_pop = InfectedPopulation(new_infected, name=self.name + '.infected')
                new_pop.infection_tx.add_consumer(self.infection_rx)
                new_pop.population_tx.add_consumer(self.population_rx)
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
                new_pop = RecoveredPopulation(new_recovered, name=self.name + '.recovered')
                new_pop.infection_tx.add_consumer(self.infection_rx)
                new_pop.population_tx.add_consumer(self.population_rx)
                self.infection_tx.add_consumer(new_pop.infection_rx)
                self.recovered.append(new_pop)
        if new_diagnosed:
            # print('Adding', new_diagnosed, 'diagnosed from', source.name)
            day = kwargs['day_after_infected']
            for pop in self.diagnosed:
                if day == pop.get_day():
                    pop.update_population(new_diagnosed)
                    break
            else:
                new_pop = DiagnosedPopulation(new_diagnosed, name=self.name + '.diagnosed')
                new_pop.infection_tx.add_consumer(self.infection_rx)
                new_pop.population_tx.add_consumer(self.population_rx)
                self.diagnosed.append(new_pop)

    def _get_group_population(self, *grps):
        total = 0
        for grp in grps:
            total += sum([p.population for p in grp])
        return total

    def time_observer(self):
        day = -1
        yield from sim.wait(0.8)
        while True:
            yield from sim.wait(1)
            day += 1
            if self.csv is not None:
                self.csv.write('{},{},{},{},{},{},{},{},{}\n'.format(
                    day,
                    self._get_group_population(*self.people_container, self.dead),
                    self._get_group_population(self.generic),
                    self._get_group_population(self.infected, self.diagnosed),
                    self._get_group_population(self.infected),
                    self._get_group_population(self.diagnosed),
                    self._get_group_population(self.recovered),
                    self._get_group_population(self.immune),
                    self._get_group_population(self.dead),
                ))
            print('Day:{}  Total:{}  Generic:{}  Total infected:{}  Infected:{}  Diagnosed:{}  Recovered:{}  Immune:{}  Dead:{}'.format(
                day,
                self._get_group_population(*self.people_container, self.dead),
                self._get_group_population(self.generic),
                self._get_group_population(self.infected, self.diagnosed),
                self._get_group_population(self.infected),
                self._get_group_population(self.diagnosed),
                self._get_group_population(self.recovered),
                self._get_group_population(self.immune),
                self._get_group_population(self.dead),
            ))

if __name__ == "__main__":
    with open('result.csv', 'w') as f:
        f.write('Day,Total,Unaffected,Total infected,Infected,Diagnosed,Recovered,Immune,Dead\n')
        gp = GenericPopulation(name="Generic", csv=f)
        sim.run(365)
    print(sim.time)
