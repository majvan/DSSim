"""
Traffic light network case study — salabim implementation.

Same design as crossroad_semaphores.py but using salabim instead of DSSim:
  - TrafficLight   → salabim.Component that updates a salabim.State
  - QueueDrainer   → salabim.Component that waits for green and flushes queues
  - Crossroad      → plain Python class: queues (lists), routing table, stats
  - VehicleGenerator → salabim.Component that creates vehicle dicts at intervals

Inter-component routing uses direct method calls (crossroad.arrive()) instead
of DSSim publishers/subscribers.

Salabim note: yieldless=False is required to use yield inside process().
Each run_*() / test_*() function creates a fresh Environment.
"""
import random
from collections import Counter, defaultdict

import salabim

# Module-level env; replaced by each test/run function before creating components.
env = None

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
# Component 1: TrafficLight
# ---------------------------------------------------------------------------
class TrafficLight(salabim.Component):
    """Cycles RED -> GREEN -> YELLOW -> RED, updating a salabim.State."""

    def setup(self, state, offset=0):
        self.light_state = state   # salabim.State shared with QueueDrainer
        self.offset      = offset

    def process(self):
        if self.offset:
            yield self.hold(self.offset)
        while True:
            self.light_state.set('red')
            yield self.hold(RED_SECS)
            self.light_state.set('green')
            yield self.hold(GREEN_SECS)
            self.light_state.set('yellow')
            yield self.hold(YELLOW_SECS)


# ---------------------------------------------------------------------------
# Component 2 helper: TravelDelay
# ---------------------------------------------------------------------------
class TravelDelay(salabim.Component):
    """Holds for a travel time, then delivers a vehicle to the next crossroad."""

    def setup(self, vehicle, next_crd, in_arm, travel_time):
        self.vehicle     = vehicle
        self.next_crd    = next_crd
        self.in_arm      = in_arm
        self.travel_time = travel_time

    def process(self):
        yield self.hold(self.travel_time)
        self.next_crd.arrive(self.vehicle, self.in_arm)


# ---------------------------------------------------------------------------
# Component 2 helper: QueueDrainer
# ---------------------------------------------------------------------------
class QueueDrainer(salabim.Component):
    """Wakes when the light turns green, flushes all queued vehicles."""

    def setup(self, crossroad, light_state, arms):
        self.crossroad   = crossroad
        self.light_state = light_state  # salabim.State
        self.arms        = arms         # list of from_arm strings

    def process(self):
        while True:
            # Wait until this light turns green
            yield self.wait((self.light_state, 'green'))

            # Flush every waiting vehicle; each picks its exit independently
            for arm in self.arms:
                while self.crossroad.queues[arm]:
                    vehicle  = self.crossroad._dequeue(arm)
                    exit_arm = self.crossroad._pick_exit(arm)
                    self.crossroad._dispatch(vehicle, exit_arm)

            # Wait until light leaves green (turns yellow) before looping back,
            # so we do not immediately re-trigger on the same green phase.
            yield self.wait((self.light_state, 'yellow'))


# ---------------------------------------------------------------------------
# Component 2: Crossroad (plain Python class — no salabim base needed)
# ---------------------------------------------------------------------------
class Crossroad:
    """One intersection with configurable turn probabilities.

    Arms:   n, s, w, e  (one queue, one entry callback, one exit per arm)
    Lights: NS (controls n/s arms) and EW (controls w/e arms)
    """

    def __init__(self, name, routing=None, ns_offset=0):
        self.name    = name
        self.routing = routing or DEFAULT_ROUTING

        # Traffic light states (shared between TrafficLight and QueueDrainer)
        self.ns_state = salabim.State(name=name + '.ns', value='red', env=env)
        self.ew_state = salabim.State(name=name + '.ew', value='red', env=env)

        # One Python list per arm — vehicles wait here when light is not green
        self.queues = {'n': [], 's': [], 'w': [], 'e': []}

        # Output connections: arm -> (next_crossroad, entry_arm) or absent = exit
        self._next = {}

        # Statistics: time-weighted queue length monitors + dequeue counters
        self.q_mon = {
            arm: salabim.Monitor(name=name + '.' + arm + '_q', level=True, env=env)
            for arm in 'nswe'
        }
        for arm in 'nswe':
            self.q_mon[arm].tally(0)          # initialise at t=0

        self._dequeue_count = Counter()        # total vehicles dequeued per arm
        self._passthrough_count = Counter()    # vehicles that passed straight through

        # Start traffic light controllers
        TrafficLight(
            name=name + '.ns_tl',
            state=self.ns_state,
            offset=ns_offset,
            env=env,
        )
        TrafficLight(
            name=name + '.ew_tl',
            state=self.ew_state,
            offset=ns_offset + GREEN_SECS + YELLOW_SECS,
            env=env,
        )

        # Start queue drainers
        QueueDrainer(
            name=name + '.ns_dr',
            crossroad=self,
            light_state=self.ns_state,
            arms=['n', 's'],
            env=env,
        )
        QueueDrainer(
            name=name + '.ew_dr',
            crossroad=self,
            light_state=self.ew_state,
            arms=['w', 'e'],
            env=env,
        )

    # ---- wiring ------------------------------------------------------------

    def connect(self, out_arm, next_crossroad, in_arm, travel_time=0):
        """Connect an output arm to another crossroad's input arm."""
        self._next[out_arm] = (next_crossroad, in_arm, travel_time)

    # ---- internal helpers --------------------------------------------------

    def _pick_exit(self, from_arm):
        """Weighted random draw from the routing table for this entry arm."""
        options = self.routing[from_arm]
        return random.choices(list(options), weights=options.values())[0]

    def _enqueue(self, arm, vehicle):
        """Add vehicle to arm queue and update the length monitor."""
        self.queues[arm].append(vehicle)
        self.q_mon[arm].tally(len(self.queues[arm]))

    def _dequeue(self, arm):
        """Remove the front vehicle from arm queue and update the monitor."""
        vehicle = self.queues[arm].pop(0)
        self.q_mon[arm].tally(len(self.queues[arm]))
        self._dequeue_count[arm] += 1
        return vehicle

    def _dispatch(self, vehicle, exit_arm):
        """Forward vehicle to the next crossroad or let it leave the grid."""
        if exit_arm in self._next:
            next_crd, in_arm, travel_time = self._next[exit_arm]
            vehicle['from_arm'] = in_arm      # update entry arm for next hop
            if travel_time:
                TravelDelay(vehicle=vehicle, next_crd=next_crd,
                            in_arm=in_arm, travel_time=travel_time, env=env)
            else:
                next_crd.arrive(vehicle, in_arm)
        # else: vehicle exits the grid — counted in dequeue_count already

    # ---- public API --------------------------------------------------------

    def arrive(self, vehicle, arm):
        """Called when a vehicle arrives at this arm from outside."""
        light_state = self.ns_state if arm in ('n', 's') else self.ew_state
        vehicle['from_arm'] = arm
        if light_state.get() == 'green':
            # Light is green — pass straight through without queuing
            exit_arm = self._pick_exit(arm)
            self._passthrough_count[arm] += 1
            self._dispatch(vehicle, exit_arm)
        else:
            # Light is red or yellow — wait in queue
            self._enqueue(arm, vehicle)

    def queue_stats(self, arm):
        """Return statistics for the given arm queue.

        get_count mirrors DSSim's QueueStatsProbe: it counts only vehicles that
        actually waited in the queue (arrived on red/yellow). Vehicles that
        passed straight through on green are tracked separately in
        _passthrough_count but not included here.
        """
        mon = self.q_mon[arm]
        return {
            'time_avg_len': mon.mean() if mon.mean() == mon.mean() else 0.0,
            'max_len':      int(mon.maximum()),
            'get_count':    self._dequeue_count[arm],
        }


# ---------------------------------------------------------------------------
# Component 3: VehicleGenerator
# ---------------------------------------------------------------------------
class VehicleGenerator(salabim.Component):
    """Creates vehicle dicts at a fixed interval and delivers them to one arm."""

    def setup(self, crossroad, arm, interval, label):
        self.crossroad = crossroad
        self.arm       = arm
        self.interval  = interval
        self.label     = label
        self._count    = 0

    def process(self):
        while True:
            yield self.hold(self.interval)
            self._count += 1
            vehicle = {
                'id':       f'{self.label}-{self._count}',
                'arrived':  env.now(),
                'from_arm': self.arm,
            }
            self.crossroad.arrive(vehicle, self.arm)


# ---------------------------------------------------------------------------
# Routing distribution test  (mirrors the DSSim test_routing())
# ---------------------------------------------------------------------------
def test_routing(routing=None, n_vehicles=300, seed=0):
    """Feed n_vehicles from north and west arms; print exit distribution."""
    global env
    random.seed(seed)
    routing = routing or URBAN_ROUTING

    env = salabim.Environment(trace=False, yieldless=False)

    crd  = Crossroad(name='A', routing=routing)
    exits = defaultdict(Counter)

    # Intercept all 4 output arms by patching _dispatch
    orig_dispatch = crd._dispatch

    def tracking_dispatch(vehicle, exit_arm):
        exits[vehicle['from_arm']].update([exit_arm])
        orig_dispatch(vehicle, exit_arm)

    crd._dispatch = tracking_dispatch

    VehicleGenerator(name='gen_n', crossroad=crd, arm='n',
                     interval=2, label='N', env=env)
    VehicleGenerator(name='gen_w', crossroad=crd, arm='w',
                     interval=2, label='W', env=env)

    env.run(till=n_vehicles * 2 + 100)

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
# 2x2 grid run  (mirrors the DSSim run_grid())
# ---------------------------------------------------------------------------
def run_grid(sim_time=3600, routing=None):
    """Run the full 2x2 crossroad grid and print queue statistics."""
    global env
    env = salabim.Environment(trace=False, yieldless=False)

    crd = {
        'A': Crossroad(name='A', routing=routing, ns_offset=0),
        'B': Crossroad(name='B', routing=routing, ns_offset=12),
        'D': Crossroad(name='D', routing=routing, ns_offset=15),
        'C': Crossroad(name='C', routing=routing, ns_offset=25),
    }

    # EW road top row: A <-> B
    crd['A'].connect('e', crd['B'], 'w')
    crd['B'].connect('w', crd['A'], 'e')
    # EW road bottom row: D <-> C
    crd['D'].connect('e', crd['C'], 'w')
    crd['C'].connect('w', crd['D'], 'e')
    # NS road left col: A <-> D
    crd['A'].connect('s', crd['D'], 'n')
    crd['D'].connect('n', crd['A'], 's')
    # NS road right col: B <-> C
    crd['B'].connect('s', crd['C'], 'n')
    crd['C'].connect('n', crd['B'], 's')

    # Entry-point vehicle generators
    VehicleGenerator(name='W-A', crossroad=crd['A'], arm='w', interval=4, label='W-A', env=env)
    VehicleGenerator(name='W-D', crossroad=crd['D'], arm='w', interval=4, label='W-D', env=env)
    VehicleGenerator(name='N-A', crossroad=crd['A'], arm='n', interval=3, label='N-A', env=env)
    VehicleGenerator(name='N-B', crossroad=crd['B'], arm='n', interval=3, label='N-B', env=env)

    env.run(till=sim_time)

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
    """Run the 2x2 grid with TravelDelay between each crossroad pair."""
    global env
    env = salabim.Environment(trace=False, yieldless=False)

    crd = {
        'A': Crossroad(name='A', routing=routing, ns_offset=0),
        'B': Crossroad(name='B', routing=routing, ns_offset=12),
        'D': Crossroad(name='D', routing=routing, ns_offset=15),
        'C': Crossroad(name='C', routing=routing, ns_offset=25),
    }

    # EW road top row: A <-> B
    crd['A'].connect('e', crd['B'], 'w', ew_delay)
    crd['B'].connect('w', crd['A'], 'e', ew_delay)
    # EW road bottom row: D <-> C
    crd['D'].connect('e', crd['C'], 'w', ew_delay)
    crd['C'].connect('w', crd['D'], 'e', ew_delay)
    # NS road left col: A <-> D
    crd['A'].connect('s', crd['D'], 'n', ns_delay)
    crd['D'].connect('n', crd['A'], 's', ns_delay)
    # NS road right col: B <-> C
    crd['B'].connect('s', crd['C'], 'n', ns_delay)
    crd['C'].connect('n', crd['B'], 's', ns_delay)

    # Entry-point vehicle generators
    VehicleGenerator(name='W-A', crossroad=crd['A'], arm='w', interval=4, label='W-A', env=env)
    VehicleGenerator(name='W-D', crossroad=crd['D'], arm='w', interval=4, label='W-D', env=env)
    VehicleGenerator(name='N-A', crossroad=crd['A'], arm='n', interval=3, label='N-A', env=env)
    VehicleGenerator(name='N-B', crossroad=crd['B'], arm='n', interval=3, label='N-B', env=env)

    env.run(till=sim_time)

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
