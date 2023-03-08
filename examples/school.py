from dssim.simulation import DSComponent, DSProcess, DSSimulation
from dssim.pubsub import DSProducer
from dssim.processcomponent import DSProcessComponent
from random import randint

class School(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx = DSProducer(name=self.name+'.bell_tx', sim=self.sim)
        DSProcess(self.school_bell(), name=self.name+'.bell_process', sim=self.sim).schedule(0)
        self.days = 0

    def school_bell(self):
        while True:
            now = self.sim.time % (24 * 60)  # get time of day in [minutes]
            if now > 8 * 60:
                yield from self.sim.gwait(24 * 60 - now)  # wait till midnight
                now = 0
            yield from self.sim.gwait(8 * 60 - now)  # wait till 8:00
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 1st class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 2nd class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(20)  # big break wait 20 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 3rd class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 4th class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 5th class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(5)  # break wait 5 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 6th class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 7th class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 8th class wait 45 minutes
            self.tx.signal('end')
            yield from self.sim.gwait(10)  # break wait 10 minutes
            self.tx.signal('start')
            yield from self.sim.gwait(45)  # 9th class wait 45 minutes
            self.tx.signal('end')
            self.days += 1

class Pupil(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx = DSProducer(name=self.name+'.brain_activity_tx', sim=self.sim)
        # self.brain_activity = 'none'
        self.total_classes = 0

    def go_to_school(self, school, nr_of_classes):
        # self.brain_activity = 'moderate'
        print(f'{self} going to school at {self.sim.time % (24*60) // 60}:{self.sim.time % 60:02d}')
        # get notified from tx
        with self.sim.observe_pre(school.tx):
            class_n = 1
            while True:
                yield from self.sim.gwait(cond=lambda e: e == 'start')
                print(f'{self} starting class #{class_n} at {self.sim.time % (24*60) // 60}:{self.sim.time % 60:02d}')
                self.tx.signal('high')
                yield from self.sim.gwait(cond=lambda e: e == 'end')
                class_n += 1
                if class_n >= nr_of_classes:
                    self.total_classes += nr_of_classes
                    break
                print(f'{self} starting break at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
            self.tx.signal('moderate')
        print(f'{self} is after school at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
        self.tx.signal('low')
        minute_in_day = self.sim.time % (24 * 60)
        event = yield from self.sim.gwait(21 * 60 - minute_in_day, cond=lambda e:True)  # play after school till 21:00
        print(f'{self} is going to sleep at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
        self.tx.signal('none')
        return 'done'

class Family(DSProcessComponent):
    def process(self, school, pupils):
        while True:
            now = sim.time % (24 * 60)  # get time of day in [minutes]
            yield from self.sim.gwait(24 * 60 - now)  # wait till midnight
            yield from self.sim.gwait(7 * 60 + 45)  # wait till 7:45
            for pupil in pupils:
                school_process = DSProcess(pupil.go_to_school(school, randint(6, 8)), sim=self.sim).schedule(0)

if __name__ == '__main__':
    sim = DSSimulation()
    school = School(name='Elementary School Newton Street', sim=sim)
    pupils = [Pupil(name=pupil_name, sim=sim) for pupil_name in ('Peter', 'John', 'Maria', 'Eva')]
    Family(school, pupils, name='Family', sim=sim)

    sim.run(24 * 60 * 30)
    assert 180 <= pupils[0].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[1].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[2].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[3].total_classes <= 220  # high probability to get into interval
