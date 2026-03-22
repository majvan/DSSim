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
Batch Chemical Reactor — DSCircuit with Independent Concurrent Conditions.

N batch reactors share M cooling-water slots and a single operator. Before
starting a reaction each reactor must have ALL five conditions simultaneously
true:

  - Temperature at setpoint  (drifts in/out — REEVALUATE)
  - Pressure at setpoint     (drifts in/out — REEVALUATE)
  - Cooling water allocated  (shared pool   — REEVALUATE)
  - Feed valve open          (re-confirms   — REEVALUATE)
  - Operator batch-release   (momentary     — PULSED)

DSCircuit features demonstrated:
  - AND composition of 5 independent asynchronous conditions
  - REEVALUATE: temp / pressure / cooling toggle on/off independently
  - REEVALUATE: feed valve re-confirms periodically (recovers after reset)
  - PULSED: operator command ignored unless all other conditions are green
  - Negation / reset: cooling header pressure drop clears all cached states
  - Source scoping via filter `eps`: events from one publisher never
    contaminate filters subscribed to a different publisher
"""
from random import uniform
from dssim import DSSimulation, DSComponent
from dssim.pubsub.pubsub import DSPub
from dssim.pubsub.cond import DSFilter


# ---------------------------------------------------------------------------
# Default timing constants (seconds)
# ---------------------------------------------------------------------------
TEMP_STABLE = (15, 25)         # time temperature stays in range
TEMP_UNSTABLE = (8, 15)        # time temperature drifts out of range
TEMP_SETPOINT = 180.0          # target temperature (°C)
TEMP_TOLERANCE = 5.0           # acceptable deviation (±°C)
PRES_STABLE = (12, 20)         # time pressure stays in range
PRES_UNSTABLE = (6, 12)        # time pressure drifts out of range
PRES_SETPOINT = 12.0           # target pressure (bar)
PRES_TOLERANCE = 0.5           # acceptable deviation (±bar)
FEED_OPEN_TIME = (1, 3)        # time to open feed valve
REACTION_TIME = (50, 70)       # reaction duration once started
OPERATOR_INTERVAL = 8          # seconds between operator visits to each reactor
COOLING_SLOTS = 2              # shared cooling-water slots
PRESSURE_DROP_INTERVAL = 1800  # cooling header pressure drop every N seconds
PRESSURE_DROP_JITTER = 0.3     # ±30 % random variation on drop timing
SIM_TIME = 4 * 3600            # 4-hour shift


# ---------------------------------------------------------------------------
# Cooling water pool — shared resource with M slots
# ---------------------------------------------------------------------------
class CoolingPool:
    """Manages M cooling-water slots among N reactors (FIFO allocation).

    Periodically suffers a transient pressure drop on the cooling header.
    The drop is published on ``drop_pub`` so that reactor circuits can use
    it as a negated reset signal.
    """

    def __init__(self, sim, slots, drop_interval=PRESSURE_DROP_INTERVAL,
                 drop_jitter=PRESSURE_DROP_JITTER):
        self.sim = sim
        self.available = slots
        self._waiting = []          # queue of Reactor instances
        self._allocated = []        # reactors currently holding a slot
        self.drop_pub = DSPub(name='cooling.drop', sim=sim)
        self.drop_interval = drop_interval
        self.drop_jitter = drop_jitter
        self.drop_count = 0

    def start(self):
        self.sim.schedule(0, self._drop_timer())

    def _drop_timer(self):
        """Periodic transient pressure drop on the cooling header.

        After the drop, pressure recovers and all allocated reactors
        receive a fresh True confirmation on their cooling_pub.
        """
        while True:
            jitter = uniform(-self.drop_jitter, self.drop_jitter)
            delay = self.drop_interval * (1 + jitter)
            yield from self.sim.gwait(delay)
            self.drop_count += 1
            self.drop_pub.signal('pressure_drop')
            # Pressure recovers after a brief dip — re-confirm cooling
            yield from self.sim.gwait(uniform(5, 15))
            for reactor in self._allocated:
                reactor.cooling_pub.signal(True)

    def request(self, reactor):
        """Reactor asks for a cooling slot. Signals immediately if available."""
        if self.available > 0:
            self.available -= 1
            self._allocated.append(reactor)
            reactor.cooling_pub.signal(True)
        else:
            self._waiting.append(reactor)

    def release(self, reactor):
        """Reactor returns its cooling slot after reaction completes."""
        if reactor not in self._allocated:
            return  # already released (e.g. by pressure drop reassignment)
        self._allocated.remove(reactor)
        reactor.cooling_pub.signal(False)
        if self._waiting:
            next_r = self._waiting.pop(0)
            self._allocated.append(next_r)
            next_r.cooling_pub.signal(True)
        else:
            self.available += 1


# ---------------------------------------------------------------------------
# Operator — visits reactors round-robin, sends PULSED release command
# ---------------------------------------------------------------------------
class Operator:
    """Single operator cycling through reactors."""

    def __init__(self, sim, reactors, operator_pub, interval=OPERATOR_INTERVAL):
        self.sim = sim
        self.reactors = reactors
        self.operator_pub = operator_pub
        self.interval = interval

    def start(self):
        self.sim.schedule(0, self._round_robin())

    def _round_robin(self):
        idx = 0
        while True:
            yield from self.sim.gwait(self.interval)
            reactor = self.reactors[idx]
            self.operator_pub.signal(reactor.reactor_id)
            idx = (idx + 1) % len(self.reactors)


# ---------------------------------------------------------------------------
# Batch reactor with DSCircuit-based startup logic
# ---------------------------------------------------------------------------
class Reactor(DSComponent):
    """A single batch reactor whose startup requires 5 simultaneous conditions."""

    def __init__(self, reactor_id, cooling_pool, operator_pub, drop_pub,
                 temp_stable=TEMP_STABLE, temp_unstable=TEMP_UNSTABLE,
                 temp_setpoint=TEMP_SETPOINT, temp_tolerance=TEMP_TOLERANCE,
                 pres_stable=PRES_STABLE, pres_unstable=PRES_UNSTABLE,
                 pres_setpoint=PRES_SETPOINT, pres_tolerance=PRES_TOLERANCE,
                 feed_open_time=FEED_OPEN_TIME, reaction_time=REACTION_TIME,
                 **kwargs):
        super().__init__(**kwargs)
        self.reactor_id = reactor_id
        self.cooling_pool = cooling_pool
        self.operator_pub = operator_pub
        self.drop_pub = drop_pub

        # Timing parameters (min, max) tuples
        self.temp_stable = temp_stable
        self.temp_unstable = temp_unstable
        self.temp_setpoint = temp_setpoint
        self.temp_tolerance = temp_tolerance
        self.pres_stable = pres_stable
        self.pres_unstable = pres_unstable
        self.pres_setpoint = pres_setpoint
        self.pres_tolerance = pres_tolerance
        self.feed_open_time = feed_open_time
        self.reaction_time = reaction_time

        # Per-reactor publishers (independent signal sources)
        self.temp_pub = DSPub(name=f'{self.name}.temp', sim=self.sim)
        self.pres_pub = DSPub(name=f'{self.name}.pres', sim=self.sim)
        self.cooling_pub = DSPub(name=f'{self.name}.cooling', sim=self.sim)
        self.feed_pub = DSPub(name=f'{self.name}.feed', sim=self.sim)

        # Metrics
        self.reactions_completed = 0
        self.total_wait_time = 0.0
        self.total_reaction_time = 0.0

    def _build_circuit(self):
        """Build DSCircuit with source-scoped filters (created once, reused every cycle)."""
        sp_t, tol_t = self.temp_setpoint, self.temp_tolerance
        sp_p, tol_p = self.pres_setpoint, self.pres_tolerance
        self.f_temp = self.sim.filter(
            cond=lambda e, s=sp_t, t=tol_t: abs(e - s) <= t,
            eps=[self.temp_pub],
            sigtype=DSFilter.SignalType.REEVALUATE,
        )
        self.f_pres = self.sim.filter(
            cond=lambda e, s=sp_p, t=tol_p: abs(e - s) <= t,
            eps=[self.pres_pub],
            sigtype=DSFilter.SignalType.REEVALUATE,
        )
        self.f_cool = self.sim.filter(
            eps=[self.cooling_pub],
            sigtype=DSFilter.SignalType.REEVALUATE,
        )
        self.f_feed = self.sim.filter(
            eps=[self.feed_pub],
            sigtype=DSFilter.SignalType.REEVALUATE,
        )
        self.f_op = self.sim.filter(
            cond=lambda e, rid=self.reactor_id: e == rid,
            eps=[self.operator_pub],
            sigtype=DSFilter.SignalType.PULSED,
        )
        self.f_drop = self.sim.filter(eps=[self.drop_pub])

        # AND of all five, with cooling pressure drop as reset.
        self.ready = (self.f_temp & self.f_pres & self.f_cool
                      & self.f_feed & self.f_op & (-self.f_drop))
        # Disable one_shot so the circuit stays attached across cycles.
        # The REEVALUATE filters naturally toggle as conditions change;
        # the circuit re-evaluates on every event.
        self.ready.set_one_shot(False)

    def start(self):
        self._build_circuit()
        # Oscillators run continuously from t=0 (with random phase offset)
        self.sim.schedule(uniform(0, 5), self._temp_oscillator())
        self.sim.schedule(uniform(0, 5), self._pres_oscillator())
        self.sim.schedule(0, self._reactor_loop())

    # -- Independent condition oscillators ----------------------------------

    def _temp_oscillator(self):
        """Temperature cycles between in-range and drifted readings."""
        sp, tol = self.temp_setpoint, self.temp_tolerance
        while True:
            # In range — publish a reading within tolerance
            self.temp_pub.signal(sp + uniform(-tol * 0.5, tol * 0.5))
            yield from self.sim.gwait(uniform(*self.temp_stable))
            # Drifted — publish a reading outside tolerance
            self.temp_pub.signal(sp + tol * uniform(1.5, 3.0))
            yield from self.sim.gwait(uniform(*self.temp_unstable))

    def _pres_oscillator(self):
        """Pressure cycles between in-range and drifted readings."""
        sp, tol = self.pres_setpoint, self.pres_tolerance
        while True:
            self.pres_pub.signal(sp + uniform(-tol * 0.5, tol * 0.5))
            yield from self.sim.gwait(uniform(*self.pres_stable))
            self.pres_pub.signal(sp + tol * uniform(1.5, 3.0))
            yield from self.sim.gwait(uniform(*self.pres_unstable))

    # -- Feed valve opener --------------------------------------------------

    def _open_feed_valve(self):
        """Opens the feed valve after a short actuator delay.

        Once open, the valve's position sensor re-confirms periodically.
        This ensures the circuit can recover after a reset clears cached
        states — the next confirmation re-establishes the filter.
        """
        yield from self.sim.gwait(uniform(*self.feed_open_time))
        while True:
            self.feed_pub.signal(True)
            yield from self.sim.gwait(5)

    # -- Main reactor loop --------------------------------------------------

    def _reactor_loop(self):
        """Acquire conditions via DSCircuit, run reaction, repeat."""
        while True:
            t0 = self.sim.time

            # Request cooling water (may queue if no slots available)
            self.cooling_pool.request(self)

            # Schedule feed-valve opening as a concurrent process
            feed_proc = self.sim.schedule(0, self._open_feed_valve())

            # Wait for the circuit to fire.
            # Filters and circuit are created once (in _build_circuit) with
            # one_shot=False, so they stay attached across cycles.  REEVALUATE
            # filters naturally toggle as oscillators publish new readings;
            # the circuit re-evaluates on every event and fires when all
            # five conditions align simultaneously.
            yield from self.ready.gwait()

            wait_time = self.sim.time - t0
            self.total_wait_time += wait_time

            # Stop the feed valve confirmation loop
            if not feed_proc.finished():
                feed_proc.abort()

            # Reaction!
            rx_time = uniform(*self.reaction_time)
            yield from self.sim.gwait(rx_time)
            self.reactions_completed += 1
            self.total_reaction_time += rx_time

            # Release cooling water for the next reactor
            self.cooling_pool.release(self)


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------
def run_simulation(n_reactors, cooling_slots=COOLING_SLOTS,
                   sim_time=SIM_TIME, operator_interval=OPERATOR_INTERVAL,
                   pressure_drop_interval=PRESSURE_DROP_INTERVAL,
                   pressure_drop_jitter=PRESSURE_DROP_JITTER,
                   temp_stable=TEMP_STABLE, temp_unstable=TEMP_UNSTABLE,
                   temp_setpoint=TEMP_SETPOINT, temp_tolerance=TEMP_TOLERANCE,
                   pres_stable=PRES_STABLE, pres_unstable=PRES_UNSTABLE,
                   pres_setpoint=PRES_SETPOINT, pres_tolerance=PRES_TOLERANCE,
                   feed_open_time=FEED_OPEN_TIME, reaction_time=REACTION_TIME):
    """Run one simulation and return a metrics dict."""
    sim = DSSimulation()
    pool = CoolingPool(sim, cooling_slots,
                       drop_interval=pressure_drop_interval,
                       drop_jitter=pressure_drop_jitter)
    operator_pub = DSPub(name='operator', sim=sim)

    reactors = []
    for i in range(n_reactors):
        r = Reactor(
            reactor_id=i,
            cooling_pool=pool,
            operator_pub=operator_pub,
            drop_pub=pool.drop_pub,
            temp_stable=temp_stable,
            temp_unstable=temp_unstable,
            temp_setpoint=temp_setpoint,
            temp_tolerance=temp_tolerance,
            pres_stable=pres_stable,
            pres_unstable=pres_unstable,
            pres_setpoint=pres_setpoint,
            pres_tolerance=pres_tolerance,
            feed_open_time=feed_open_time,
            reaction_time=reaction_time,
            name=f'reactor-{i}',
            sim=sim,
        )
        reactors.append(r)
        r.start()

    pool.start()
    operator = Operator(sim, reactors, operator_pub, interval=operator_interval)
    operator.start()

    sim.run(until=sim_time)

    hours = sim_time / 3600
    total_completed = sum(r.reactions_completed for r in reactors)
    total_wait = sum(r.total_wait_time for r in reactors)
    total_rx = sum(r.total_reaction_time for r in reactors)
    n_reactions = max(total_completed, 1)

    return {
        'n_reactors': n_reactors,
        'cooling_slots': cooling_slots,
        'total_completed': total_completed,
        'throughput_per_hour': total_completed / hours,
        'per_reactor_per_hour': total_completed / (hours * n_reactors),
        'avg_wait_time': total_wait / n_reactions,
        'avg_reaction_time': total_rx / n_reactions,
        'cooling_utilisation': min(total_rx / (sim_time * cooling_slots), 1.0),
        'pressure_drops': pool.drop_count,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print(f"{'N':>3}  {'done':>5}  {'tput/hr':>8}  {'per-rx/hr':>10}  "
          f"{'avg_wait':>9}  {'cool_util':>10}")
    print('-' * 55)
    for n in [1, 2, 3, 4, 6, 8, 10, 12]:
        r = run_simulation(n_reactors=n)
        print(f"{r['n_reactors']:3d}  {r['total_completed']:5d}  "
              f"{r['throughput_per_hour']:8.1f}  "
              f"{r['per_reactor_per_hour']:10.2f}  "
              f"{r['avg_wait_time']:9.1f}  "
              f"{r['cooling_utilisation']:10.1%}")
