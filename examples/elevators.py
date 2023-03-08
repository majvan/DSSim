from math import floor
from dssim.processcomponent import DSProcessComponent
from dssim.pubsub import DSProducer
from dssim.simulation import DSCallback

class Person(DSProcessComponent):
    def __init__(self, init_floor, requested_floor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_floor = init_floor
        self.requested_floor = requested_floor
        self.elevator = None

    def process(self):
        elevator = yield from self.person_waiting()
        yield from self.person_moving(elevator)

    def person_waiting(self):
        if self.requested_floor > self.init_floor:
            self.direction = 'up'
        elif self.requested_floor < self.init_floor:
            self.direction = 'down'
        else:
            return
        start_waiting_time = self.sim.time
        while self.elevator is None:
            already_waiting = self.sim.time() - start_waiting_time
            elevators = yield from self.init_floor.wait_for_elevator(60 - already_waiting)  # wait max. 60 seconds
            if elevators is None:
                return  # decided to take stairs instead
            # Policy to choose an elevator from the elevators follows. Choose first one which can go our direction
            elevators = [el for el in self.init_floor.get_waiting_elevators() if self.direction in el.get_directions()]
            if len(elevators) > 0:
                return elevators[0]

    def person_moving(self, elevator):
        elevator.enter(self)
        elevator.add_request(self.requested_floor)
        yield from elevator.wait_for_floor(self.requested_floor)
        elevator.leave(self)

class Floor(DSProcessComponent):
    def __init__(self, nr, elevators, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nr = nr
        self.elevators = elevators
        self.events_from_elevators = [el.arrival_tx for el in self.elevators]
        self.people_waiting = []
        self.requests = set()

    def push_button(self, command):
        if command not in self.requests:
            # choose elevator to send the request
            elevator = self.elevators[0]
            elevator.add_request_from_floor(self, self.nr, command)

    def get_waiting_elevators(self, direction):
        return [e for e in self.elevators if e.stopped and e.last_floor == self.nr and direction in e.directions]

    def wait_for_elevator(self, direction, timeout=float('inf')):
        retval = yield from self.sim.check_and_wait(timeout, lambda e:len(self.get_waiting_elevators(direction)) > 0)
        return retval

    def process(self):
        with self.sim.observe(*self.events_from_elevators):
            while True:
                elevator = yield from self.wait_for_elevator(lambda e:True)  # wait for any elevator to come
                if 'down' in elevator.directions:
                    self.requests.remove('down')
                else:  # 'up' in elevator.directions
                    self.requests.remove('up')


class Elevator(DSProcessComponent):
    def __init__(self, max_speed, floors, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.speed = 4  # 4 seconds per floors
        self.last_floor = 0
        self.stopped = True
        self.internal_requests = set()
        self.external_requests = set()
        self.container = []
        self.max_load = 100
        self.directions = ('up', 'down')
        self.requests_tx = DSProducer(name=self.name+'.requests (internal)')
        self.arrival_tx = DSProducer(name=self.name+'.arrival')

    def enter(self, obj):
        self.container.append(obj)

    def leave(self, obj):
        self.container.remove(obj)

    def add_request_from_floor(self, floor, direction):
        self.external_requests.add((floor, direction))
        self.requests_tx.signal(event='from floor')

    def add_request_from_elevator(self, floor):
        self.internal_requests.add(floor)
        if self.directions == ('up', 'down'):  # if not decided yet about the direction, first request in elevator decides
            if floor > self.last_floor:
                self.directions = ('up',)
            elif floor < self.last_floor:
                self.directions = ('down',)
        self.requests_tx.signal(event='from elevator')

    def get_directions(self):
        return self.directions

    def get_current_position(self):
        if self.stopped:
            retval = self.last_floor
        elif 'up' in self.directions:
            retval = (self.sim.time - self.last_floor_time) / self.speed + self.last_floor
        else:  # 'down' in self.directions
            retval = self.last_floor - (self.sim.time - self.last_floor_time) / self.speed
        return retval

    def process(self):
        while True:
            # In this state we wait for the first request. We are willing to go any direction.
            self.directions = ('up', 'down')  # ready to go up or down
            self.internal_requests = set()
            self.stopped = True
            with self.sim.consume(self.requests_tx):
                obj = yield from self.sim.check_and_wait(cond=len(self.internal_requests) + len(self.external_requests) > 0)
            if self.sim.is_event(obj) and obj['event'] == 'from elevator':
                yield from self.sim.gwait(10)  # timeout for closing door
            self.last_floor_time = self.sim.time()
            while len(self.internal_requests) + len(self.external_requests) > 0:
                # Policy to select the next destination based on the requests and direction
                if 'up' in self.directions:
                    floors_in_direction = set(floor for floor, dir in self.external_requests if floor > self.get_current_position() and dir == 'up')
                    floors_in_direction |= set(floor for floor in self.internal_requests if floor > self.get_current_position())
                    if len(floors_in_direction) > 0:
                        next_floor = max(floors_in_direction)
                    else:  # if no command in our direction, then try command down from a floor which is upper
                        calls = set(floor for floor, dir in self.external_requests if floor > self.get_current_position() and dir == 'down')
                        if len(calls) > 0:
                            next_floor = max(calls)
                        else:
                            self.directions = ('up',)
                            continue  # re-evaluate
                    self.directions = ('up',)
                else:  # 'down' in self.directions
                    floors_in_direction = set(floor for floor, dir in self.external_requests if floor < self.get_current_position() and dir == 'down')
                    floors_in_direction |= set(floor for floor in self.internal_requests if floor > self.get_current_position())
                    if len(floors_in_direction) > 0:
                        next_floor = max(floors_in_direction)
                    else:  # if no command in our direction, then try command up from a floor which is below
                        calls = set(floor for floor, dir in self.external_requests if floor < self.get_current_position() and dir == 'up')
                        if len(calls) > 0:
                            next_floor = min(calls)
                        else:
                            self.directions = ('up',)
                            continue  # re-evaluate
                    self.directions = ('down',)
                if next_floor != self.next_floor:
                    next_delta = abs(self.get_current_position() - next_floor) * self.speed
                    self.next_floor = next_floor
                    self.next_time = self.sim.time + next_delta
                    self.stopped = False
                else:
                    next_delta = self.next_time - self.sim.time
                # Wait for the next change in the requests or for the event we reach the next floor
                with self.sim.consume(self.requests_tx):
                    obj = yield from self.sim.gwait(next_delta, cond=lambda e:True)  # get any new request event
                if obj is None:
                    # new floor reached
                    self.last_floor = self.next_floor
                    self.stopped = True
                    self.external_requests.remove(self.last_floor)
                    self.internal_requests.remove(self.last_floor)
                    self.arrival_tx.signal(event='arrived')
                    yield from self.sim.gwait(10)  # timeout for closing door
                    if len(self.container) == 0:
                        break

                else:
                    # we got a new request and hence we may recompute the destinations
                    pass

