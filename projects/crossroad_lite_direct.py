# Copyright 2026- majvan (majvan@gmail.com)
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
Traffic light network case study — DSSim LiteLayer2, direct-binding implementation.

Components wire directly via ISubscriber objects.
Delayed links use one reusable delayed subscriber per connection:

  - TrafficLight  → notifies a plain list of callables on each state change
  - Crossroad     → _out[arm] holds a subscriber (or None); each input arm is
                    an ISubscriber endpoint (`n_in`, `s_in`, `w_in`, `e_in`)
  - delays        → make_delayed(sim, sub, t) returns an ISubscriber that
                    schedules to the target subscriber after `t`
"""
import random
from bisect import bisect
from collections import deque
from collections import Counter, defaultdict

from dssim import DSSimulation, LiteLayer2
from dssim.base import EventType, ISubscriber

# ---------------------------------------------------------------------------
# Light timing constants
# ---------------------------------------------------------------------------
GREEN_SECS  = 30
YELLOW_SECS = 5
RED_SECS    = 30

# ---------------------------------------------------------------------------
# Routing tables
# ---------------------------------------------------------------------------
DEFAULT_ROUTING = {
    'n': {'s': 1.0},
    's': {'n': 1.0},
    'w': {'e': 1.0},
    'e': {'w': 1.0},
}

URBAN_ROUTING = {
    'n': {'s': 0.70, 'e': 0.20, 'w': 0.10},
    's': {'n': 0.70, 'w': 0.20, 'e': 0.10},
    'w': {'e': 0.60, 'n': 0.25, 's': 0.15},
    'e': {'w': 0.60, 's': 0.25, 'n': 0.15},
}


# ---------------------------------------------------------------------------
# Manual queue statistics
# ---------------------------------------------------------------------------
class QueueStats:
    """Time-weighted queue length statistics accumulated manually."""

    def __init__(self, sim):
        self._sim       = sim
        self._len       = 0
        self._area      = 0.0
        self._last_t    = 0.0
        self._max       = 0
        self._get_count = 0

    def _flush(self):
        now = self._sim.time
        self._area  += self._len * (now - self._last_t)
        self._last_t = now

    def tally(self, new_len):
        self._flush()
        self._len = new_len
        if new_len > self._max:
            self._max = new_len

    def on_dequeue(self):
        self._get_count += 1

    def stats(self):
        self._flush()
        avg = self._area / self._sim.time if self._sim.time > 0 else 0.0
        return {
            'time_avg_len': avg,
            'max_len':      self._max,
            'get_count':    self._get_count,
        }


# ---------------------------------------------------------------------------
# Delay helper — no DSLiteDelay, no generators per vehicle
# ---------------------------------------------------------------------------
class _ArmInSubscriber(ISubscriber):
    supports_direct_send = True

    def __init__(self, crossroad, arm):
        self._crossroad = crossroad
        self._arm = arm

    def send(self, event: EventType):
        self._crossroad._arrive(self._arm, event)
        return True


class _DelayedSubscriber(ISubscriber):
    supports_direct_send = True

    def __init__(self, sim, target_subscriber: ISubscriber, delay_time):
        self._sim = sim
        self._target = target_subscriber
        self._delay = delay_time

    def send(self, event: EventType):
        self._sim.schedule_event(self._delay, event, self._target)
        return True


def make_delayed(sim, target_subscriber: ISubscriber, delay_time):
    """Return a subscriber that forwards to target_subscriber after delay_time."""
    return _DelayedSubscriber(sim, target_subscriber, delay_time)


# ---------------------------------------------------------------------------
# Component 1: TrafficLight
# ---------------------------------------------------------------------------
class TrafficLight:
    """Cycles RED -> GREEN -> YELLOW -> RED indefinitely.

    Notifies a plain list of callables on each state change — no DSLitePub.
    """

    CYCLE = [('red', RED_SECS), ('green', GREEN_SECS), ('yellow', YELLOW_SECS)]

    def __init__(self, sim, name):
        self.sim   = sim
        self.name  = name
        self.state = 'red'
        self._listeners = []   # plain Python callables: fn(state) -> None
        self._task = None

    def add_listener(self, fn):
        self._listeners.append(fn)

    def start(self, offset=0):
        if self._task is not None:
            return
        self._task = self._run(offset)
        self.sim.schedule(0, self._task)

    def stop(self):
        if self._task is None:
            return
        self.sim.cleanup(self._task)
        try:
            self._task.close()
        except ValueError:
            # Already-running generators cannot be closed safely at this point.
            pass
        self._task = None

    def _run(self, offset):
        if offset:
            yield from self.sim.gsleep(offset)
        while True:
            for state, duration in self.CYCLE:
                self.state = state
                for fn in self._listeners:
                    fn(state)
                yield from self.sim.gsleep(duration)


# ---------------------------------------------------------------------------
# Component 2: Crossroad
# ---------------------------------------------------------------------------
class Crossroad:
    """One intersection with configurable turn probabilities.

    Arms:   n, s, w, e
    Lights: NS (controls n/s arms) and EW (controls w/e arms)

    _out[arm] is an ISubscriber (or None if the arm exits the grid).
    Input arms are ISubscriber endpoints: n_in / s_in / w_in / e_in.
    """

    def __init__(self, sim, name, routing=None):
        self.sim     = sim
        self.name    = name
        self.routing = routing or DEFAULT_ROUTING

        self.ns_light = TrafficLight(sim, name + '.ns')
        self.ew_light = TrafficLight(sim, name + '.ew')

        self.queues  = {'n': deque(), 's': deque(), 'w': deque(), 'e': deque()}
        self.q_stats = {arm: QueueStats(sim) for arm in 'nswe'}
        self._routing_cache = self._build_routing_cache(self.routing)

        # Input endpoints: one ISubscriber per arm.
        self.n_in = _ArmInSubscriber(self, 'n')
        self.s_in = _ArmInSubscriber(self, 's')
        self.w_in = _ArmInSubscriber(self, 'w')
        self.e_in = _ArmInSubscriber(self, 'e')

        # Direct output: arm -> ISubscriber or None
        self._out = {'n': None, 's': None, 'w': None, 'e': None}

        self.ns_light.add_listener(self._on_ns)
        self.ew_light.add_listener(self._on_ew)

    # ---- wiring ------------------------------------------------------------

    def connect(self, out_arm, subscriber):
        """Wire an output arm to an ISubscriber (or delayed wrapper)."""
        self._out[out_arm] = subscriber

    # ---- internal helpers --------------------------------------------------

    @staticmethod
    def _build_routing_cache(routing):
        cache = {}
        for from_arm, options in routing.items():
            exits = tuple(options.keys())
            cum_weights = []
            total = 0.0
            for w in options.values():
                total += w
                cum_weights.append(total)
            cache[from_arm] = (exits, tuple(cum_weights), total)
        return cache

    def _pick_exit(self, from_arm):
        exits, cum_weights, total = self._routing_cache[from_arm]
        rnd = random.random() * total
        idx = bisect(cum_weights, rnd)
        return exits[idx]

    def _enqueue(self, arm, vehicle):
        self.queues[arm].append(vehicle)
        self.q_stats[arm].tally(len(self.queues[arm]))

    def _dequeue(self, arm):
        vehicle = self.queues[arm].popleft()
        self.q_stats[arm].tally(len(self.queues[arm]))
        self.q_stats[arm].on_dequeue()
        return vehicle

    def _forward(self, vehicle, exit_arm):
        subscriber = self._out[exit_arm]
        if subscriber:
            subscriber.send(vehicle)

    def _arrive(self, arm, vehicle):
        light = self.ns_light if arm in ('n', 's') else self.ew_light
        vehicle['from_arm'] = arm
        if light.state == 'green':
            self._forward(vehicle, self._pick_exit(arm))
        else:
            self._enqueue(arm, vehicle)

    def _on_ns(self, state):
        if state == 'green':
            self._drain('n')
            self._drain('s')

    def _on_ew(self, state):
        if state == 'green':
            self._drain('w')
            self._drain('e')

    def _drain(self, arm):
        while self.queues[arm]:
            vehicle = self._dequeue(arm)
            self._forward(vehicle, self._pick_exit(arm))

    # ---- public API --------------------------------------------------------

    def start(self, ns_offset=0):
        self.ns_light.start(offset=ns_offset)
        self.ew_light.start(offset=ns_offset + GREEN_SECS + YELLOW_SECS)

    def stop(self):
        self.ns_light.stop()
        self.ew_light.stop()

    def queue_stats(self, arm):
        return self.q_stats[arm].stats()


# ---------------------------------------------------------------------------
# Component 3: VehicleGenerator
# ---------------------------------------------------------------------------
class VehicleGenerator:
    """Creates vehicles at a fixed interval and sends them to a subscriber."""

    def __init__(self, sim, subscriber, interval, label):
        self.sim      = sim
        self.subscriber = subscriber
        self.interval = interval
        self.label    = label
        self._count   = 0
        self._task    = None

    def start(self):
        if self._task is not None:
            return
        self._task = self._run()
        self.sim.schedule(0, self._task)

    def stop(self):
        if self._task is None:
            return
        self.sim.cleanup(self._task)
        try:
            self._task.close()
        except ValueError:
            # Already-running generators cannot be closed safely at this point.
            pass
        self._task = None

    def _run(self):
        while True:
            yield from self.sim.gsleep(self.interval)
            self._count += 1
            vehicle = {'id': f'{self.label}-{self._count}', 'arrived': self.sim.time}
            self.subscriber.send(vehicle)


# ---------------------------------------------------------------------------
# Routing distribution test
# ---------------------------------------------------------------------------
def test_routing(routing=None, n_vehicles=300, seed=0):
    """Feed n_vehicles from north and west arms; print exit distribution."""
    random.seed(seed)
    routing = routing or URBAN_ROUTING

    sim = DSSimulation(layer2=LiteLayer2)
    crd = Crossroad(sim, name='A', routing=routing)

    exits = defaultdict(Counter)

    # Patch _forward to observe exits
    orig_forward = crd._forward
    def tracking_forward(vehicle, exit_arm):
        exits[vehicle['from_arm']].update([exit_arm])
        orig_forward(vehicle, exit_arm)
    crd._forward = tracking_forward

    def feeder(subscriber, label):
        for _ in range(n_vehicles):
            yield from sim.gsleep(2)
            subscriber.send({'from_arm': label})

    crd.start()
    feeder_n = feeder(crd.n_in, 'n')
    feeder_w = feeder(crd.w_in, 'w')
    sim.schedule(0, feeder_n)
    sim.schedule(0, feeder_w)
    sim.run(until=n_vehicles * 4)
    crd.stop()
    for feeder_task in (feeder_n, feeder_w):
        sim.cleanup(feeder_task)
        try:
            feeder_task.close()
        except ValueError:
            pass

    for from_arm, label in [('n', 'north entry'), ('w', 'west entry')]:
        total = sum(exits[from_arm].values())
        if total == 0:
            print(f"\n{label}: no vehicles recorded")
            continue
        print(f"\n{label} ({total} vehicles):")
        for to_arm in sorted(exits[from_arm]):
            cnt = exits[from_arm][to_arm]
            exp = routing[from_arm].get(to_arm, 0) * 100
            print(f"  exit {to_arm}: {cnt:4d}  ({100*cnt/total:.0f}%,  expected {exp:.0f}%)")


# ---------------------------------------------------------------------------
# 2x2 grid run
# ---------------------------------------------------------------------------
def run_grid(sim_time=3600, routing=None):
    """Run the full 2x2 crossroad grid and print queue statistics."""
    sim = DSSimulation(layer2=LiteLayer2)

    crd = {k: Crossroad(sim, name=k, routing=routing) for k in 'ABCD'}

    # EW road top row: A <-> B
    crd['A'].connect('e', crd['B'].w_in)
    crd['B'].connect('w', crd['A'].e_in)
    # EW road bottom row: D <-> C
    crd['D'].connect('e', crd['C'].w_in)
    crd['C'].connect('w', crd['D'].e_in)
    # NS road left col: A <-> D
    crd['A'].connect('s', crd['D'].n_in)
    crd['D'].connect('n', crd['A'].s_in)
    # NS road right col: B <-> C
    crd['B'].connect('s', crd['C'].n_in)
    crd['C'].connect('n', crd['B'].s_in)

    crd['A'].start(ns_offset=0)
    crd['B'].start(ns_offset=12)
    crd['D'].start(ns_offset=15)
    crd['C'].start(ns_offset=25)

    generators = [
        VehicleGenerator(sim, crd['A'].w_in, 4, 'W-A'),
        VehicleGenerator(sim, crd['D'].w_in, 4, 'W-D'),
        VehicleGenerator(sim, crd['A'].n_in, 3, 'N-A'),
        VehicleGenerator(sim, crd['B'].n_in, 3, 'N-B'),
    ]
    for g in generators:
        g.start()

    sim.run(until=sim_time)
    for g in generators:
        g.stop()
    for x in crd.values():
        x.stop()

    print(f"\n{'Queue':<10} {'avg len':>8} {'max len':>8} {'total':>8}")
    print("-" * 40)
    for name in 'ABCD':
        for arm in ('n', 'w'):
            s = crd[name].queue_stats(arm)
            key = f'{name}_{arm}'
            print(f"{key:<10} {s['time_avg_len']:>8.2f} {s['max_len']:>8} {s['get_count']:>8}")


# ---------------------------------------------------------------------------
# 2x2 grid run with inter-crossroad travel delays
# ---------------------------------------------------------------------------
def run_grid_with_delays(sim_time=3600, routing=None, ew_delay=12, ns_delay=15):
    """Run the 2x2 grid with travel delays between each crossroad pair."""
    sim = DSSimulation(layer2=LiteLayer2)

    crd = {k: Crossroad(sim, name=k, routing=routing) for k in 'ABCD'}

    def wire(out_arm, src, dst_subscriber, delay):
        src.connect(out_arm, make_delayed(sim, dst_subscriber, delay))

    # EW road top row: A <-> B
    wire('e', crd['A'], crd['B'].w_in, ew_delay)
    wire('w', crd['B'], crd['A'].e_in, ew_delay)
    # EW road bottom row: D <-> C
    wire('e', crd['D'], crd['C'].w_in, ew_delay)
    wire('w', crd['C'], crd['D'].e_in, ew_delay)
    # NS road left col: A <-> D
    wire('s', crd['A'], crd['D'].n_in, ns_delay)
    wire('n', crd['D'], crd['A'].s_in, ns_delay)
    # NS road right col: B <-> C
    wire('s', crd['B'], crd['C'].n_in, ns_delay)
    wire('n', crd['C'], crd['B'].s_in, ns_delay)

    crd['A'].start(ns_offset=0)
    crd['B'].start(ns_offset=12)
    crd['D'].start(ns_offset=15)
    crd['C'].start(ns_offset=25)

    generators = [
        VehicleGenerator(sim, crd['A'].w_in, 4, 'W-A'),
        VehicleGenerator(sim, crd['D'].w_in, 4, 'W-D'),
        VehicleGenerator(sim, crd['A'].n_in, 3, 'N-A'),
        VehicleGenerator(sim, crd['B'].n_in, 3, 'N-B'),
    ]
    for g in generators:
        g.start()

    sim.run(until=sim_time)
    for g in generators:
        g.stop()
    for x in crd.values():
        x.stop()

    print(f"\n{'Queue':<10} {'avg len':>8} {'max len':>8} {'total':>8}")
    print("-" * 40)
    for name in 'ABCD':
        for arm in ('n', 'w'):
            s = crd[name].queue_stats(arm)
            key = f'{name}_{arm}'
            print(f"{key:<10} {s['time_avg_len']:>8.2f} {s['max_len']:>8} {s['get_count']:>8}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=== Routing distribution test (urban turns) ===")
    test_routing(routing=URBAN_ROUTING)

    print("\n=== 2x2 grid, 1-hour run (straight-through) ===")
    run_grid(sim_time=3600, routing=DEFAULT_ROUTING)

    print("\n=== 2x2 grid with travel delays (aligned green wave: 12s EW, 15s NS) ===")
    run_grid_with_delays(sim_time=3600, routing=DEFAULT_ROUTING, ew_delay=12, ns_delay=15)

    print("\n=== 2x2 grid with travel delays (misaligned: 20s EW, 22s NS) ===")
    run_grid_with_delays(sim_time=3600, routing=DEFAULT_ROUTING, ew_delay=20, ns_delay=22)
