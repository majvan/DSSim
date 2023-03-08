# Copyright 2021 NXP Semiconductors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Elevator from salabim examples
The user can set some values: number of floors, number of elevator cabins,
capacity of the cabins (persons) and the number of visitors requesting an elevator.
The default values set in the code are as follows:
    Number of floors: topfloor = 15
    Number of elevator cabins: ncars = 3
    Capacity of each cabin: capacity = 4
    Number of visitors requesting a lift:
        From level 0 to level n: load_0_n = 50
        From level n to level n: load_n_n = 100
        From level n to level 0: load_n_0 = 100
"""
from dssim.simulation import DSSimulation
from dssim.processcomponent import DSProcessComponent
from dssim.components.queue import Queue
import random


class VisitorGenerator(DSProcessComponent):
    def __init__(self, from_, to, id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.from_ = from_
        self.to = to
        self.id = id

    def process(self):
        while True:
            from_ = random.randint(self.from_[0], self.from_[1])
            while True:
                to = random.randint(self.to[0], self.to[1])
                if from_ != to:
                    break

            Visitor(from_=from_, to=to)
            if self.id == "0_n":
                load = load_0_n
            elif self.id == "n_0":
                load = load_0_n
            else:
                load = load_n_n

            if load == 0:
                return
            else:
                iat = 3600 / load
                r = random.uniform(0.5, 1.5)
                yield from self.sim.gwait(r * iat)


class Visitor(DSProcessComponent):
    def __init__(self, from_, to, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fromfloor = floors[from_]
        self.tofloor = floors[to]
        self.direction = getdirection(self.fromfloor, self.tofloor)
        print(f'Generating {self} from {from_} to {to}')


    def process(self):
        self.enter_nowait(self.fromfloor.visitors)
        if not (self.fromfloor, self.direction) in requests:
            requests[self.fromfloor, self.direction] = self.sim.time
        for car in cars:
            car.signal('visitor waiting')

        yield from self.sim.gwait(cond=lambda e:True)


class Car(DSProcessComponent):
    def __init__(self, capacity, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capacity = capacity
        self.direction = still
        self.floor = floors[0]
        self.visitors = Queue(name=self.name+".visitors in car")

    def process(self):
        dooropen = False
        self.floor = floors[0]
        self.direction = still
        dooropen = False
        while True:
            if self.direction == still:
                if not requests:
                    yield from self.sim.gwait(cond=lambda e:True)
            if self.count_to_floor(self.floor) > 0:
                yield from self.sim.gwait(dooropen_time)
                dooropen = True
                for visitor in self.visitors:
                    if visitor.tofloor == self.floor:
                        visitor.leave(self.visitors)
                        print(f'{visitor} left {self} at floor {self.floor.n}')
                        visitor.signal('out from car')
                yield from self.sim.gwait(exit_time)

            if self.direction == still:
                self.direction = up  # just random

            for self.direction in (self.direction, -self.direction):
                if (self.floor, self.direction) in requests:
                    del requests[self.floor, self.direction]

                    if not dooropen:
                        yield from self.sim.gwait(dooropen_time)
                        dooropen = True
                    for visitor in self.floor.visitors:
                        if visitor.direction == self.direction:
                            if len(self.visitors) < self.capacity:
                                visitor.leave(self.floor.visitors)
                                visitor.enter_nowait(self.visitors)
                                print(f'{visitor} enter {self} at floor {self.floor.n}')
                        yield from self.sim.gwait(enter_time)
                    if self.floor.count_in_direction(self.direction) > 0:
                        if not (self.floor, self.direction) in requests:
                            requests[self.floor, self.direction] = self.sim.time

                if self.visitors:
                    break
            else:
                if requests:
                    earliest = float('inf')
                    for (floor, direction) in requests:
                        if requests[floor, direction] < earliest:
                            self.direction = getdirection(self.floor, floor)
                            earliest = requests[floor, direction]
                else:
                    self.direction = still
            if dooropen:
                yield from self.sim.gwait(doorclose_time)
                dooropen = False

            if self.direction != still:
                self.nextfloor = floors[self.floor.n + self.direction]
                yield from self.sim.gwait(move_time)
                self.floor = self.nextfloor
                print(f'{self} on floor {self.floor.n}')

    def count_to_floor(self, tofloor):
        n = 0
        for visitor in self.visitors:
            if visitor.tofloor == tofloor:
                n += 1
        return n


class Floor:
    def __init__(self, n):
        self.n = n
        self.visitors = Queue(name=f"visitors {n}")

    def count_in_direction(self, dir):
        n = 0
        for visitor in self.visitors:
            if visitor.direction == dir:
                n += 1
        return n

def getdirection(fromfloor, tofloor):
    if fromfloor.n < tofloor.n:
        return +1
    if fromfloor.n > tofloor.n:
        return -1
    return 0


sim = DSSimulation()
up = 1
still = 0
down = -1

move_time = 10
dooropen_time = 3
doorclose_time = 3
enter_time = 3
exit_time = 3

load_0_n = 50
load_n_n = 100
load_n_0 = 100
capacity = 4
ncars = 3
topfloor = 15

VisitorGenerator(from_=(0, 0), to=(1, topfloor), id="0_n", name="vg_0_n")
VisitorGenerator(from_=(1, topfloor), to=(0, 0), id="n_0", name="vg_n_0")
VisitorGenerator(from_=(1, topfloor), to=(1, topfloor), id="n_n", name="vg_n_n")

requests = {}
floors = {ifloor: Floor(ifloor) for ifloor in range(topfloor + 1)}
cars = [Car(capacity=capacity) for icar in range(ncars)]

sim.run(10000)
