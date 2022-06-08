from dssim.simulation import sim, DSComponent, DSProcess
from dssim.pubsub import DSProducer
from random import randint

class School(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx = DSProducer(name=self.name+'.bell_tx')
        self.sim.schedule(0, DSProcess(self.school_bell(), name=self.name+'.bell_process'))
        self.days = 0

    def school_bell(self):
        while True:
            now = self.sim.time % (24 * 60)  # get time of day in [minutes]
            if now > 8 * 60:
                yield from self.sim.wait(24 * 60 - now)  # wait till midnight
                now = 0
            yield from self.sim.wait(8 * 60 - now)  # wait till 8:00
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 1st class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 2nd class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(20)  # big break wait 20 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 3rd class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 4th class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 5th class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(5)  # break wait 5 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 6th class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 7th class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 8th class wait 45 minutes
            self.tx.signal(bell='end')
            yield from self.sim.wait(10)  # break wait 10 minutes
            self.tx.signal(bell='start')
            yield from self.sim.wait(45)  # 9th class wait 45 minutes
            self.tx.signal(bell='end')
            self.days += 1

class Pupil(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx = DSProducer(name=self.name+'.brain_activity_tx')
        self.brain_activity = 'none'
        self.total_classes = 0

    def go_to_school(self, school, nr_of_classes):
        self.brain_activity = 'moderate'
        print(f'{self} going to school at {self.sim.time % (24*60) // 60}:{self.sim.time % 60:02d}')
        # get notified from tx
        with self.sim.observe_pre(school.tx):
            class_n = 1
            while True:
                yield from self.sim.wait(cond=lambda e: e['bell'] == 'start')
                print(f'{self} starting class #{class_n} at {self.sim.time % (24*60) // 60}:{self.sim.time % 60:02d}')
                self.tx.signal(activity='high')
                yield from self.sim.wait(cond=lambda e: e['bell'] == 'end')
                class_n += 1
                if class_n >= nr_of_classes:
                    self.total_classes += nr_of_classes
                    break
                print(f'{self} starting break at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
            self.tx.signal(activity='moderate')
        print(f'{self} is after school at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
        self.tx.signal(activity='low')
        minute_in_day = self.sim.time % (24 * 60)
        event = yield from self.sim.wait(21 * 60 - minute_in_day, cond=lambda e:True)  # play after school till 21:00
        print(f'{self} is going to sleep at {self.sim.time % (24 * 60) // 60}:{self.sim.time % 60:02d}')
        self.tx.signal(activity='none')
        return 'done'

def family_life(school, pupils):
    while True:
        now = sim.time % (24 * 60)  # get time of day in [minutes]
        yield from sim.wait(24 * 60 - now)  # wait till midnight
        yield from sim.wait(7 * 60 + 45)  # wait till 7:45
        for pupil in pupils:
            school_process = sim.schedule(0, DSProcess(pupil.go_to_school(school, randint(6, 8))))

if __name__ == '__main__':
    school = School(name='Elementary School Newton Street')
    pupils = [Pupil(name=pupil_name) for pupil_name in ('Peter', 'John', 'Maria', 'Eva')]
    sim.schedule(0, DSProcess(family_life(school, pupils)))

    sim.run(24 * 60 * 30)
    assert 180 <= pupils[0].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[1].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[2].total_classes <= 220  # high probability to get into interval
    assert 180 <= pupils[3].total_classes <= 220  # high probability to get into interval
