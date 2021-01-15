"""
Traffic light network case study — SimPy implementation.

Same design as crossroad_semaphores.py but using SimPy:
  - TrafficLight    → process that cycles states; fires a one-shot env.event()
                      on each green phase (replaced every cycle)
  - QueueDrainer    → process per light that yields the green event and flushes queues
  - Crossroad       → plain Python class: queues, routing table, manual stats
  - VehicleGenerator → process that creates vehicle dicts at fixed intervals

Inter-component routing uses direct arrive() calls (no pub/sub).
Travel delays use short-lived env.process() instances (one per vehicle in transit).
"""
import random
from collections import Counter, defaultdict

import simpy

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
# Manual queue statistics (no built-in probes in SimPy)
# ---------------------------------------------------------------------------
class QueueStats:
    """Time-weighted queue length statistics accumulated manually."""

    def __init__(self, env):
        self._env       = env
        self._len       = 0
        self._area      = 0.0
        self._last_t    = 0.0
        self._max       = 0
        self._get_count = 0

    def _flush(self):
        now = self._env.now
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
        avg = self._area / self._env.now if self._env.now > 0 else 0.0
        return {
            'time_avg_len': avg,
            'max_len':      self._max,
            'get_count':    self._get_count,
        }


# ---------------------------------------------------------------------------
# Component 1: TrafficLight
# ---------------------------------------------------------------------------
class TrafficLight:
    """Cycles RED -> GREEN -> YELLOW -> RED indefinitely.

    self.green is a one-shot simpy.Event fired at each green phase onset.
    It is replaced with a fresh event immediately after firing so that
    QueueDrainer can yield the *next* green event after the current one.
    """

    CYCLE = [('red', RED_SECS), ('green', GREEN_SECS), ('yellow', YELLOW_SECS)]

    def __init__(self, env, name, offset=0):
        self.env   = env
        self.name  = name
        self.state = 'red'
        self.green = env.event()          # current "turn green" trigger
        env.process(self._run(offset))

    def _run(self, offset):
        if offset:
            yield self.env.timeout(offset)
        while True:
            for state, duration in self.CYCLE:
                self.state = state
                if state == 'green':
                    self.green.succeed()      # wake any waiters
                    self.green = self.env.event()  # arm next cycle's event
                yield self.env.timeout(duration)


# ---------------------------------------------------------------------------
# Component 2: Crossroad
# ---------------------------------------------------------------------------
class Crossroad:
    """One intersection with configurable turn probabilities.

    Arms:   n, s, w, e  (one queue per arm)
    Lights: NS (controls n/s arms) and EW (controls w/e arms)

    Vehicles arriving on a green arm pass through immediately.
    Vehicles arriving on red/yellow queue and are released by QueueDrainer
    processes that wake on each green event.
    """

    def __init__(self, env, name, routing=None, ns_offset=0):
        self.env     = env
        self.name    = name
        self.routing = routing or DEFAULT_ROUTING

        self.ns_light = TrafficLight(env, name + '.ns', offset=ns_offset)
        self.ew_light = TrafficLight(env, name + '.ew',
                                     offset=ns_offset + GREEN_SECS + YELLOW_SECS)

        # One plain list per arm — vehicles wait here when light is red/yellow
        self.queues = {'n': [], 's': [], 'w': [], 'e': []}

        # Queue statistics per arm
        self.q_stats = {arm: QueueStats(env) for arm in 'nswe'}

        # Output connections: arm -> (next_crossroad, entry_arm, travel_time)
        self._next = {}

        self._passthrough_count = Counter()

        # Start queue-drainer processes
        env.process(self._drain_loop(self.ns_light, ('n', 's')))
        env.process(self._drain_loop(self.ew_light, ('w', 'e')))

    # ---- wiring ------------------------------------------------------------

    def connect(self, out_arm, next_crossroad, in_arm, travel_time=0):
        """Connect an output arm to another crossroad's input arm."""
        self._next[out_arm] = (next_crossroad, in_arm, travel_time)

    # ---- internal helpers --------------------------------------------------

    def _pick_exit(self, from_arm):
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

    def _dispatch(self, vehicle, exit_arm):
        """Forward vehicle to the next crossroad or let it leave the grid."""
        if exit_arm not in self._next:
            return  # vehicle exits the grid
        next_crd, in_arm, travel_time = self._next[exit_arm]
        vehicle['from_arm'] = in_arm
        if travel_time:
            self.env.process(self._travel(vehicle, next_crd, in_arm, travel_time))
        else:
            next_crd.arrive(vehicle, in_arm)

    def _travel(self, vehicle, next_crd, in_arm, travel_time):
        """Short-lived process that models travel time between crossroads."""
        yield self.env.timeout(travel_time)
        next_crd.arrive(vehicle, in_arm)

    def _drain_loop(self, light, arms):
        """Process: wait for green, flush all queued vehicles on those arms."""
        while True:
            yield light.green          # wait for the next green event
            for arm in arms:
                while self.queues[arm]:
                    vehicle  = self._dequeue(arm)
                    exit_arm = self._pick_exit(arm)
                    self._dispatch(vehicle, exit_arm)

    # ---- public API --------------------------------------------------------

    def arrive(self, vehicle, arm):
        """Called when a vehicle arrives at this arm."""
        light = self.ns_light if arm in ('n', 's') else self.ew_light
        vehicle['from_arm'] = arm
        if light.state == 'green':
            exit_arm = self._pick_exit(arm)
            self._passthrough_count[arm] += 1
            self._dispatch(vehicle, exit_arm)
        else:
            self._enqueue(arm, vehicle)

    def queue_stats(self, arm):
        return self.q_stats[arm].stats()


# ---------------------------------------------------------------------------
# Component 3: VehicleGenerator
# ---------------------------------------------------------------------------
class VehicleGenerator:
    """Creates vehicle dicts at a fixed interval and delivers them to one arm."""

    def __init__(self, env, crossroad, arm, interval, label):
        self.env       = env
        self.crossroad = crossroad
        self.arm       = arm
        self.interval  = interval
        self.label     = label
        self._count    = 0
        env.process(self._run())

    def _run(self):
        while True:
            yield self.env.timeout(self.interval)
            self._count += 1
            vehicle = {
                'id':       f'{self.label}-{self._count}',
                'arrived':  self.env.now,
                'from_arm': self.arm,
            }
            self.crossroad.arrive(vehicle, self.arm)


# ---------------------------------------------------------------------------
# Routing distribution test
# ---------------------------------------------------------------------------
def test_routing(routing=None, n_vehicles=300, seed=0):
    """Feed n_vehicles from north and west arms; print exit distribution."""
    random.seed(seed)
    routing = routing or URBAN_ROUTING

    env = simpy.Environment()
    crd = Crossroad(env, name='A', routing=routing)

    exits = defaultdict(Counter)

    # Intercept all dispatches by patching _dispatch
    orig_dispatch = crd._dispatch

    def tracking_dispatch(vehicle, exit_arm):
        exits[vehicle['from_arm']].update([exit_arm])
        orig_dispatch(vehicle, exit_arm)

    crd._dispatch = tracking_dispatch

    def feeder(crossroad, arm, n):
        for _ in range(n):
            yield env.timeout(2)
            env.step()  # let any now-queue events fire first
            crossroad.arrive({'from_arm': arm}, arm)

    env.process(feeder(crd, 'n', n_vehicles))
    env.process(feeder(crd, 'w', n_vehicles))
    env.run(until=n_vehicles * 4)

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
    env = simpy.Environment()

    crd = {
        'A': Crossroad(env, name='A', routing=routing, ns_offset=0),
        'B': Crossroad(env, name='B', routing=routing, ns_offset=12),
        'D': Crossroad(env, name='D', routing=routing, ns_offset=15),
        'C': Crossroad(env, name='C', routing=routing, ns_offset=25),
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

    VehicleGenerator(env, crd['A'], 'w', 4, 'W-A')
    VehicleGenerator(env, crd['D'], 'w', 4, 'W-D')
    VehicleGenerator(env, crd['A'], 'n', 3, 'N-A')
    VehicleGenerator(env, crd['B'], 'n', 3, 'N-B')

    env.run(until=sim_time)

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
    env = simpy.Environment()

    crd = {
        'A': Crossroad(env, name='A', routing=routing, ns_offset=0),
        'B': Crossroad(env, name='B', routing=routing, ns_offset=12),
        'D': Crossroad(env, name='D', routing=routing, ns_offset=15),
        'C': Crossroad(env, name='C', routing=routing, ns_offset=25),
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

    VehicleGenerator(env, crd['A'], 'w', 4, 'W-A')
    VehicleGenerator(env, crd['D'], 'w', 4, 'W-D')
    VehicleGenerator(env, crd['A'], 'n', 3, 'N-A')
    VehicleGenerator(env, crd['B'], 'n', 3, 'N-B')

    env.run(until=sim_time)

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
