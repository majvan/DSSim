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
Traffic light network case study — DSSim LiteLayer2 implementation.

Same design as crossroad_semaphores.py but using DSSimulation(layer2=LiteLayer2):
  - TrafficLight    → plain class; generator _run() drives the light cycle
  - Crossroad       → plain class; sim.publisher()/sim.callback() for wiring
  - VehicleGenerator → plain class; generator _run() emits vehicles at intervals

Key differences from the PubSubLayer2 version:
  - yield from sim.gsleep() replaces await self.sim.sleep()
  - sim.schedule(0, gen) replaces sim.process(gen).schedule(0)
  - sim.publisher() / sim.callback() / sim.delay() replace direct DSLite* construction
  - No stats probes (not available in LiteLayer2); QueueStats tracks manually
"""
import random
from collections import Counter, defaultdict

from dssim import DSSimulation, LiteLayer2

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
# Manual queue statistics (replaces DSQueueStatsProbe)
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
# Component 1: TrafficLight
# ---------------------------------------------------------------------------
class TrafficLight:
    """Cycles RED -> GREEN -> YELLOW -> RED indefinitely."""

    CYCLE = [('red', RED_SECS), ('green', GREEN_SECS), ('yellow', YELLOW_SECS)]

    def __init__(self, sim, name):
        self.sim   = sim
        self.name  = name
        self.state = 'red'
        self.tx    = sim.publisher(name=name + '.tx')

    def start(self, offset=0):
        self.sim.schedule(0, self._run(offset))

    def _run(self, offset):
        if offset:
            yield from self.sim.gsleep(offset)
        while True:
            for state, duration in self.CYCLE:
                self.state = state
                self.sim.signal(state, self.tx)
                yield from self.sim.gsleep(duration)


# ---------------------------------------------------------------------------
# Component 2: Crossroad
# ---------------------------------------------------------------------------
class Crossroad:
    """One intersection with configurable turn probabilities.

    Arms:   n, s, w, e  (one queue, one input callback, one output publisher)
    Lights: NS (controls n/s arms) and EW (controls w/e arms)
    """

    def __init__(self, sim, name, routing=None):
        self.sim     = sim
        self.name    = name
        self.routing = routing or DEFAULT_ROUTING

        self.ns_light = TrafficLight(sim, name + '.ns')
        self.ew_light = TrafficLight(sim, name + '.ew')

        # One plain list per arm — vehicles wait here when light is not green
        self.queues = {'n': [], 's': [], 'w': [], 'e': []}

        # Queue statistics per arm
        self.q_stats = {arm: QueueStats(sim) for arm in 'nswe'}

        # Input endpoints — one per arm (rx)
        self.n_in = sim.callback(self._arrive_n, name=name + '.n_in')
        self.s_in = sim.callback(self._arrive_s, name=name + '.s_in')
        self.w_in = sim.callback(self._arrive_w, name=name + '.w_in')
        self.e_in = sim.callback(self._arrive_e, name=name + '.e_in')

        # Output endpoints — one per arm (tx)
        self.n_out = sim.publisher(name=name + '.n_out')
        self.s_out = sim.publisher(name=name + '.s_out')
        self.w_out = sim.publisher(name=name + '.w_out')
        self.e_out = sim.publisher(name=name + '.e_out')

        self._out = {'n': self.n_out, 's': self.s_out,
                     'w': self.w_out, 'e': self.e_out}

        # Subscribe to light state changes
        self.ns_light.tx.add_subscriber(sim.callback(self._on_ns, name=name + '.on_ns'))
        self.ew_light.tx.add_subscriber(sim.callback(self._on_ew, name=name + '.on_ew'))

    # ---- internal helpers --------------------------------------------------

    def _pick_exit(self, from_arm):
        """Weighted random draw from the routing table for this entry arm."""
        options = self.routing[from_arm]
        return random.choices(list(options), weights=options.values())[0]

    def _enqueue(self, arm, vehicle):
        self.queues[arm].append(vehicle)
        self.q_stats[arm].tally(len(self.queues[arm]))

    def _dequeue(self, arm):
        vehicle = self.queues[arm].pop(0)
        self.q_stats[arm].tally(len(self.queues[arm]))
        self.q_stats[arm].on_dequeue()
        return vehicle

    def _arrive(self, arm, vehicle):
        """Common arrival handler for any arm."""
        light = self.ns_light if arm in ('n', 's') else self.ew_light
        vehicle['from_arm'] = arm
        if light.state == 'green':
            self.sim.signal(vehicle, self._out[self._pick_exit(arm)])
        else:
            self._enqueue(arm, vehicle)

    def _arrive_n(self, vehicle): self._arrive('n', vehicle)
    def _arrive_s(self, vehicle): self._arrive('s', vehicle)
    def _arrive_w(self, vehicle): self._arrive('w', vehicle)
    def _arrive_e(self, vehicle): self._arrive('e', vehicle)

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
            self.sim.signal(vehicle, self._out[self._pick_exit(arm)])

    # ---- public API --------------------------------------------------------

    def start(self, ns_offset=0):
        """Start both lights. ns_offset staggers the intersection for green-wave tuning."""
        self.ns_light.start(offset=ns_offset)
        self.ew_light.start(offset=ns_offset + GREEN_SECS + YELLOW_SECS)

    def queue_stats(self, arm):
        return self.q_stats[arm].stats()


# ---------------------------------------------------------------------------
# Component 3: VehicleGenerator
# ---------------------------------------------------------------------------
class VehicleGenerator:
    """Creates vehicles at a fixed interval and signals them to one arm."""

    def __init__(self, sim, endpoint, interval, label):
        self.sim      = sim
        self.endpoint = endpoint
        self.interval = interval
        self.label    = label
        self._count   = 0

    def start(self):
        self.sim.schedule(0, self._run())

    def _run(self):
        while True:
            yield from self.sim.gsleep(self.interval)
            self._count += 1
            vehicle = {'id': f'{self.label}-{self._count}', 'arrived': self.sim.time}
            self.sim.signal(vehicle, self.endpoint)


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
    for arm in 'nswe':
        out = crd._out[arm]
        out.add_subscriber(sim.callback(
            lambda v, a=arm: exits[v['from_arm']].update([a]),
            name=f'obs_{arm}',
        ))

    def feeder(endpoint, label):
        for _ in range(n_vehicles):
            yield from sim.gsleep(2)
            sim.signal({'from_arm': label}, endpoint)

    crd.start()
    sim.schedule(0, feeder(crd.n_in, 'n'))
    sim.schedule(0, feeder(crd.w_in, 'w'))
    sim.run(until=n_vehicles * 4)

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
    crd['A'].e_out.add_subscriber(crd['B'].w_in)
    crd['B'].w_out.add_subscriber(crd['A'].e_in)
    # EW road bottom row: D <-> C
    crd['D'].e_out.add_subscriber(crd['C'].w_in)
    crd['C'].w_out.add_subscriber(crd['D'].e_in)
    # NS road left col: A <-> D
    crd['A'].s_out.add_subscriber(crd['D'].n_in)
    crd['D'].n_out.add_subscriber(crd['A'].s_in)
    # NS road right col: B <-> C
    crd['B'].s_out.add_subscriber(crd['C'].n_in)
    crd['C'].n_out.add_subscriber(crd['B'].s_in)

    # Green-wave offsets
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

    def wire(src_pub, dst_cb, delay, name):
        d = sim.delay(delay, name=name)
        src_pub.add_subscriber(d.rx)
        d.tx.add_subscriber(dst_cb)

    # EW road top row: A <-> B
    wire(crd['A'].e_out, crd['B'].w_in, ew_delay, 'A_to_B')
    wire(crd['B'].w_out, crd['A'].e_in, ew_delay, 'B_to_A')
    # EW road bottom row: D <-> C
    wire(crd['D'].e_out, crd['C'].w_in, ew_delay, 'D_to_C')
    wire(crd['C'].w_out, crd['D'].e_in, ew_delay, 'C_to_D')
    # NS road left col: A <-> D
    wire(crd['A'].s_out, crd['D'].n_in, ns_delay, 'A_to_D')
    wire(crd['D'].n_out, crd['A'].s_in, ns_delay, 'D_to_A')
    # NS road right col: B <-> C
    wire(crd['B'].s_out, crd['C'].n_in, ns_delay, 'B_to_C')
    wire(crd['C'].n_out, crd['B'].s_in, ns_delay, 'C_to_B')

    # Green-wave offsets
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
