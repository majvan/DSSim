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
Traffic light network case study.

2x2 grid of crossroads (A=NW, B=NE, C=SE, D=SW), bidirectional roads.
Each crossroad has 4 arms (N/S/E/W), each arm has its own queue.
Vehicles choose their exit direction based on a configurable routing table.
"""
import random
from collections import Counter, defaultdict

from dssim import DSSimulation, DSComponent

# ---------------------------------------------------------------------------
# Light timing constants
# ---------------------------------------------------------------------------
GREEN_SECS  = 30
YELLOW_SECS = 5
RED_SECS    = 30

# ---------------------------------------------------------------------------
# Default routing: straight through on every arm
# ---------------------------------------------------------------------------
DEFAULT_ROUTING = {
    'n': {'s': 1.0},
    's': {'n': 1.0},
    'w': {'e': 1.0},
    'e': {'w': 1.0},
}

# Typical urban routing — most vehicles go straight, some turn
URBAN_ROUTING = {
    'n': {'s': 0.70, 'e': 0.20, 'w': 0.10},
    's': {'n': 0.70, 'w': 0.20, 'e': 0.10},
    'w': {'e': 0.60, 'n': 0.25, 's': 0.15},
    'e': {'w': 0.60, 's': 0.25, 'n': 0.15},
}


# ---------------------------------------------------------------------------
# Component 1: TrafficLight
# ---------------------------------------------------------------------------
class TrafficLight(DSComponent):
    """Cycles RED -> GREEN -> YELLOW -> RED indefinitely."""

    CYCLE = [('red', RED_SECS), ('green', GREEN_SECS), ('yellow', YELLOW_SECS)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = 'red'
        self.tx = self.sim.publisher(name=self.name + '.tx')

    def start(self, offset=0):
        """Begin cycling. offset (s) delays the first transition."""
        self.sim.process(self._run(offset)).schedule(0)

    async def _run(self, offset):
        if offset:
            await self.sim.sleep(offset)
        while True:
            for state, duration in self.CYCLE:
                self.state = state
                self.sim.signal(state, self.tx)
                await self.sim.sleep(duration)


# ---------------------------------------------------------------------------
# Component 2: Crossroad (with routing extension)
# ---------------------------------------------------------------------------
class Crossroad(DSComponent):
    """One intersection with configurable turn probabilities.

    Endpoints (rx): n_in, s_in, w_in, e_in — one per physical arm
    Endpoints (tx): n_out, s_out, w_out, e_out — one per physical arm
    Queues:         n_queue, s_queue, w_queue, e_queue — one per arm
    """

    def __init__(self, routing=None, **kwargs):
        super().__init__(**kwargs)

        self.routing  = routing or DEFAULT_ROUTING

        self.ns_light = TrafficLight(name=self.name + '.ns', sim=self.sim)
        self.ew_light = TrafficLight(name=self.name + '.ew', sim=self.sim)

        # One queue per arm
        self.n_queue = self.sim.queue(name=self.name + '.n_q')
        self.s_queue = self.sim.queue(name=self.name + '.s_q')
        self.w_queue = self.sim.queue(name=self.name + '.w_q')
        self.e_queue = self.sim.queue(name=self.name + '.e_q')

        # Input endpoints — one per physical arm (rx)
        self.n_in = self.sim.callback(self._arrive_n, name=self.name + '.n_in')
        self.s_in = self.sim.callback(self._arrive_s, name=self.name + '.s_in')
        self.w_in = self.sim.callback(self._arrive_w, name=self.name + '.w_in')
        self.e_in = self.sim.callback(self._arrive_e, name=self.name + '.e_in')

        # Output endpoints — one per physical arm (tx)
        self.n_out = self.sim.publisher(name=self.name + '.n_out')
        self.s_out = self.sim.publisher(name=self.name + '.s_out')
        self.w_out = self.sim.publisher(name=self.name + '.w_out')
        self.e_out = self.sim.publisher(name=self.name + '.e_out')

        # Lookup: arm name -> publisher (built after publishers exist)
        self._out = {'n': self.n_out, 's': self.s_out,
                     'w': self.w_out, 'e': self.e_out}

        # React to light state changes
        self.ns_light.tx.add_subscriber(self.sim.callback(self._on_ns))
        self.ew_light.tx.add_subscriber(self.sim.callback(self._on_ew))

    def _pick_exit(self, from_arm):
        """Weighted random draw from the routing table for this entry arm."""
        options = self.routing[from_arm]
        return random.choices(list(options), weights=options.values())[0]

    def start(self, ns_offset=0):
        """Start both lights. ns_offset staggers the whole intersection for green-wave tuning."""
        self.ns_light.start(offset=ns_offset)
        # EW starts only after the NS green+yellow phase clears, so both lights
        # are never green at the same time.
        self.ew_light.start(offset=ns_offset + GREEN_SECS + YELLOW_SECS)

    def _arrive_n(self, vehicle):
        # Vehicle enters from the north; pick exit now if light is green,
        # otherwise queue and pick at release time.
        if self.ns_light.state == 'green':
            self.sim.signal(vehicle, self._out[self._pick_exit('n')])
        else:
            self.n_queue.put_nowait(vehicle)

    def _arrive_s(self, vehicle):
        if self.ns_light.state == 'green':
            self.sim.signal(vehicle, self._out[self._pick_exit('s')])
        else:
            self.s_queue.put_nowait(vehicle)

    def _arrive_w(self, vehicle):
        if self.ew_light.state == 'green':
            self.sim.signal(vehicle, self._out[self._pick_exit('w')])
        else:
            self.w_queue.put_nowait(vehicle)

    def _arrive_e(self, vehicle):
        if self.ew_light.state == 'green':
            self.sim.signal(vehicle, self._out[self._pick_exit('e')])
        else:
            self.e_queue.put_nowait(vehicle)

    def _on_ns(self, state):
        # NS light changed state. On green, release all queued NS vehicles,
        # each independently choosing its exit direction.
        if state == 'green':
            self._drain(self.n_queue, 'n')
            self._drain(self.s_queue, 's')

    def _on_ew(self, state):
        if state == 'green':
            self._drain(self.w_queue, 'w')
            self._drain(self.e_queue, 'e')

    def _drain(self, queue, from_arm):
        # Flush every waiting vehicle; each picks its exit from the routing table.
        while len(queue):
            item = queue.get_nowait()
            if item is None:
                break
            self.sim.signal(item, self._out[self._pick_exit(from_arm)])


# ---------------------------------------------------------------------------
# Component 3: VehicleGenerator
# ---------------------------------------------------------------------------
class VehicleGenerator:
    """Creates vehicles at a fixed interval and signals them to an endpoint."""

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
            yield from self.sim.gwait(self.interval)
            self._count += 1
            vehicle = {'id': f'{self.label}-{self._count}', 'arrived': self.sim.time}
            self.sim.signal(vehicle, self.endpoint)


# ---------------------------------------------------------------------------
# Routing extension isolated test
# ---------------------------------------------------------------------------
def test_routing(routing=None, n_vehicles=300, seed=0):
    """Feed n_vehicles from north and west arms; print exit distribution."""
    random.seed(seed)
    routing = routing or URBAN_ROUTING

    sim = DSSimulation()
    crd = Crossroad(name='A', routing=routing, sim=sim)

    exits = defaultdict(Counter)
    for arm in 'nswe':
        out = getattr(crd, arm + '_out')
        out.add_subscriber(sim.callback(lambda v, a=arm: exits[v['from']].update([a])))

    def feeder(endpoint, label):
        for _ in range(n_vehicles):
            yield from sim.gwait(2)
            sim.signal({'from': label}, endpoint)

    crd.start()
    sim.schedule(0, feeder(crd.n_in, 'n'))
    sim.schedule(0, feeder(crd.w_in, 'w'))
    sim.run(until=n_vehicles * 4)

    for from_arm, label in [('n', 'north entry'), ('w', 'west entry')]:
        total = sum(exits[from_arm].values())
        print(f"\n{label} ({total} vehicles):")
        for to_arm in sorted(exits[from_arm]):
            cnt = exits[from_arm][to_arm]
            exp = routing[from_arm].get(to_arm, 0) * 100
            print(f"  exit {to_arm}: {cnt:4d}  ({100*cnt/total:.0f}%,  expected {exp:.0f}%)")


# ---------------------------------------------------------------------------
# System integration — 2x2 grid
# ---------------------------------------------------------------------------
def run_grid(sim_time=3600, routing=None):
    """Run the full 2x2 crossroad grid and print queue statistics."""
    sim = DSSimulation()

    crd = {k: Crossroad(name=k, routing=routing, sim=sim) for k in 'ABCD'}

    # Probes on the active queues (one-way traffic uses n and w arms only)
    probes = {}
    for name, c in crd.items():
        probes[f'{name}_n'] = c.n_queue.add_stats_probe()
        probes[f'{name}_w'] = c.w_queue.add_stats_probe()

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

    # Entry-point vehicle generators
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
    for key, probe in probes.items():
        s = probe.stats()
        print(f"{key:<10} {s['time_avg_len']:>8.2f} {s['max_len']:>8} {s['get_count']:>8}")


# ---------------------------------------------------------------------------
# Bonus: 2x2 grid with inter-crossroad travel delays
# ---------------------------------------------------------------------------
def run_grid_with_delays(sim_time=3600, routing=None, ew_delay=12, ns_delay=15):
    """Run the 2x2 grid with DSDelay components between each crossroad pair.

    ew_delay — travel time (s) between east-west neighbours (A-B, D-C)
    ns_delay — travel time (s) between north-south neighbours (A-D, B-C)
    """
    sim = DSSimulation()

    crd = {k: Crossroad(name=k, routing=routing, sim=sim) for k in 'ABCD'}

    probes = {}
    for name, c in crd.items():
        probes[f'{name}_n'] = c.n_queue.add_stats_probe()
        probes[f'{name}_w'] = c.w_queue.add_stats_probe()

    def wire(src_pub, dst_cb, delay, name):
        d = sim.delay(delay, name=name)
        src_pub.add_subscriber(d.rx)
        d.tx.add_subscriber(dst_cb)

    # EW top row: A <-> B
    wire(crd['A'].e_out, crd['B'].w_in, ew_delay, 'A_to_B')
    wire(crd['B'].w_out, crd['A'].e_in, ew_delay, 'B_to_A')
    # EW bottom row: D <-> C
    wire(crd['D'].e_out, crd['C'].w_in, ew_delay, 'D_to_C')
    wire(crd['C'].w_out, crd['D'].e_in, ew_delay, 'C_to_D')
    # NS left col: A <-> D
    wire(crd['A'].s_out, crd['D'].n_in, ns_delay, 'A_to_D')
    wire(crd['D'].n_out, crd['A'].s_in, ns_delay, 'D_to_A')
    # NS right col: B <-> C
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
    for key, probe in probes.items():
        s = probe.stats()
        print(f"{key:<10} {s['time_avg_len']:>8.2f} {s['max_len']:>8} {s['get_count']:>8}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=== Routing distribution test (straight-through) ===")
    test_routing(routing=DEFAULT_ROUTING)

    print("\n=== Routing distribution test (urban turns) ===")
    test_routing(routing=URBAN_ROUTING)

    print("\n=== 2x2 grid, 1-hour run (straight-through) ===")
    run_grid(sim_time=3600, routing=DEFAULT_ROUTING)

    print("\n=== 2x2 grid with travel delays (aligned green wave: 12s EW, 15s NS) ===")
    run_grid_with_delays(sim_time=3600, routing=DEFAULT_ROUTING, ew_delay=12, ns_delay=15)

    print("\n=== 2x2 grid with travel delays (misaligned: 20s EW, 22s NS) ===")
    run_grid_with_delays(sim_time=3600, routing=DEFAULT_ROUTING, ew_delay=20, ns_delay=22)
