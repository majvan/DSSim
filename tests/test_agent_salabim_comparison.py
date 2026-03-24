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
'''
Behavior comparison: salabim hold/activate/passivate flow vs DSSim DSAgent flow.

The scenario intentionally uses:
- hold()
- activate()
- passivate()
and compares compact probe statistics side-by-side.
'''
import unittest

from dssim import DSSimulation, DSAgent

try:
    import salabim as sal
    SALABIM_AVAILABLE = True
except Exception:
    sal = None
    SALABIM_AVAILABLE = False


class _SalabimStatsProbe:
    '''Minimal probe for salabim components with compact DSAgent-like stats.'''

    def __init__(self, now: float = 0.0, state: str = 'scheduled') -> None:
        self._start_time = float(now)
        self._last_time = float(now)
        self._current_state = state
        self._state_time = {state: 0.0}
        self.event_count = 0
        self.state_event_count = 0
        self.action_event_count = 0
        self.reason_counts = {}
        self.state_entry_counts = {}

    def _advance(self, now: float) -> None:
        dt = float(now) - self._last_time
        if dt <= 0:
            return
        self._state_time[self._current_state] = self._state_time.get(self._current_state, 0.0) + dt
        self._last_time = float(now)

    def set_state(self, now: float, state: str, reason: str) -> None:
        self._advance(now)
        self.event_count += 1
        self.state_event_count += 1
        self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1
        self._current_state = state
        self._state_time.setdefault(state, 0.0)
        self.state_entry_counts[state] = self.state_entry_counts.get(state, 0) + 1

    def action(self, now: float, reason: str) -> None:
        self._advance(now)
        self.event_count += 1
        self.action_event_count += 1
        self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1

    def stats(self, now: float) -> dict:
        self._advance(now)
        return {
            'duration': float(now) - self._start_time,
            'event_count': self.event_count,
            'state_event_count': self.state_event_count,
            'action_event_count': self.action_event_count,
            'current_state': self._current_state,
            'state_time': dict(self._state_time),
            'reason_counts': dict(self.reason_counts),
            'state_entry_counts': dict(self.state_entry_counts),
        }


@unittest.skipUnless(SALABIM_AVAILABLE, 'salabim is not installed in this environment.')
class TestAgentSalabimComparison(unittest.TestCase):
    def _run_salabim_example(self) -> dict:
        env = sal.Environment(trace=False)
        probe = _SalabimStatsProbe(now=env.now(), state='scheduled')
        worker = None

        class Worker(sal.Component):
            def process(self):
                probe.set_state(env.now(), 'running', 'process_start')
                self.hold(2)
                probe.action(env.now(), 'hold')
                self.passivate()
                probe.action(env.now(), 'passivate')
                self.hold(1)
                probe.action(env.now(), 'hold')
                probe.set_state(env.now(), 'finished', 'process_finish')

        class Activator(sal.Component):
            def process(self):
                self.hold(5)
                probe.action(env.now(), 'activate')
                worker.activate()

        worker = Worker()
        Activator()
        env.run(till=10)
        return probe.stats(env.now())

    def _run_dssim_agent_example(self) -> dict:
        sim = DSSimulation()

        class Worker(DSAgent):
            def process(self):
                yield from self.hold(2)
                yield from self.passivate()
                yield from self.hold(1)

        class Activator(DSAgent):
            def __init__(self, target: Worker, *args, **kwargs):
                self.target = target
                super().__init__(*args, **kwargs)

            def process(self):
                yield from self.hold(5)
                self.target.activate('wake')

        worker = Worker(sim=sim)
        probe = worker.add_stats_probe()
        Activator(worker, sim=sim)
        sim.run(10)
        return probe.stats()

    def test1_compare_salabim_and_dssim_stats(self):
        sal_stats = self._run_salabim_example()
        ds_stats = self._run_dssim_agent_example()

        # Core parity expectations
        self.assertAlmostEqual(ds_stats['duration'], sal_stats['duration'], places=6)
        self.assertEqual(ds_stats['event_count'], sal_stats['event_count'])
        self.assertEqual(ds_stats['state_event_count'], sal_stats['state_event_count'])
        self.assertEqual(ds_stats['action_event_count'], sal_stats['action_event_count'])
        self.assertEqual(ds_stats['current_state'], sal_stats['current_state'])
        self.assertEqual(ds_stats['reason_counts'], sal_stats['reason_counts'])

        # State-time parity for this deterministic setup.
        for state_name, expected in sal_stats['state_time'].items():
            self.assertAlmostEqual(ds_stats['state_time'].get(state_name, 0.0), expected, places=6)


if __name__ == '__main__':
    unittest.main()

