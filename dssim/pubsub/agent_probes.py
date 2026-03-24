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
DSAgent probes implemented via pubsub observation on agent.tx_changed.
'''
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional, TYPE_CHECKING, TextIO

from dssim.base import DSComponent
from dssim.pubsub.pubsub import DSPub, DSSub

if TYPE_CHECKING:
    from dssim.pubsub.agent import DSAgent
    from dssim.simulation import DSSimulation


class AgentHistoryProbe(DSSub):
    '''Capture all events from agent.tx_changed and render readable history logs.'''

    def __init__(
        self,
        enabled: bool = True,
        name: str = 'history_probe',
        sim: Optional['DSSimulation'] = None,
        max_events: Optional[int] = None,
    ) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self.max_events = max_events
        self._agent: Optional['DSAgent'] = None
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._start_time: float = 0.0
        self._last_time: float = 0.0

    def attach(self, agent: 'DSAgent') -> None:
        self._agent = agent
        agent.tx_changed.add_subscriber(self, DSPub.Phase.PRE)
        self.reset()

    def close(self) -> None:
        agent = self._agent
        if agent is None:
            return
        agent.tx_changed.remove_subscriber(self, DSPub.Phase.PRE)
        self._agent = None

    def reset(self) -> None:
        now = float(self._agent.sim.time) if self._agent is not None else 0.0
        self._start_time = now
        self._last_time = now
        self._events.clear()

    def _snapshot(self, event: Any) -> Dict[str, Any]:
        if isinstance(event, dict):
            snapshot = dict(event)
            details = snapshot.get('details')
            if isinstance(details, dict):
                snapshot['details'] = dict(details)
            return snapshot
        now = float(self._agent.sim.time) if self._agent is not None else 0.0
        return {
            'kind': 'agent_event',
            'time': now,
            'raw_event': event,
        }

    def send(self, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return None
        snapshot = self._snapshot(event)
        if 'time' not in snapshot:
            snapshot['time'] = float(self._agent.sim.time)
        self._last_time = float(snapshot.get('time', self._last_time))
        self._events.append(snapshot)
        return None

    def history(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def get_history(self) -> List[Dict[str, Any]]:
        return self.history()

    def format_history(self, include_details: bool = True, with_header: bool = True) -> str:
        events = self.history()
        if len(events) == 0:
            return 'No history events.'

        lines: List[str] = []
        if with_header:
            subject = str(self._agent) if self._agent is not None else '<detached>'
            lines.append(f'Agent history: {subject} ({len(events)} events)')

        for idx, event in enumerate(events, start=1):
            time_value = float(event.get('time', 0.0))
            change_type = str(event.get('change_type', '?'))
            state = str(event.get('state', '?'))
            prev_state = event.get('prev_state')
            reason = str(event.get('reason', ''))

            if change_type == 'state' and prev_state is not None and prev_state != state:
                line = f'[{idx:03d}] t={time_value:g} {prev_state} -> {state} ({reason})'
            else:
                line = f'[{idx:03d}] t={time_value:g} {change_type}:{state} ({reason})'

            if include_details:
                details = event.get('details')
                if isinstance(details, dict) and len(details) > 0:
                    rendered = ', '.join(f'{k}={details[k]!r}' for k in sorted(details.keys()))
                    line = f'{line} | {rendered}'
            lines.append(line)

        return '\n'.join(lines)

    def dump_history(self, file: Optional[TextIO] = None, include_details: bool = True, with_header: bool = True) -> str:
        text = self.format_history(include_details=include_details, with_header=with_header)
        if file is None:
            print(text)
        else:
            file.write(text)
            if not text.endswith('\n'):
                file.write('\n')
        return text


class AgentStatsProbe(DSSub):
    '''Aggregate agent tx_changed events into compact statistics.'''

    def __init__(self, enabled: bool = True, name: str = 'stats_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._agent: Optional['DSAgent'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._current_state: str = 'unknown'
        self._state_time: Dict[str, float] = {}
        self.reset()

    def attach(self, agent: 'DSAgent') -> None:
        self._agent = agent
        agent.tx_changed.add_subscriber(self, DSPub.Phase.PRE)
        self.reset()

    def close(self) -> None:
        agent = self._agent
        if agent is None:
            return
        agent.tx_changed.remove_subscriber(self, DSPub.Phase.PRE)
        self._agent = None

    def reset(self) -> None:
        now = float(self._agent.sim.time) if self._agent is not None else 0.0
        self._start_time = now
        self._last_time = now
        self._current_state = getattr(self._agent, 'state', 'unknown')
        self._state_time = {self._current_state: 0.0}

        self.event_count = 0
        self.state_event_count = 0
        self.action_event_count = 0
        self.reason_counts: Dict[str, int] = {}
        self.state_entry_counts: Dict[str, int] = {}

    def _advance(self, now: float) -> None:
        dt = now - self._last_time
        if dt <= 0:
            return
        self._state_time[self._current_state] = self._state_time.get(self._current_state, 0.0) + dt
        self._last_time = now

    def send(self, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return None
        if not isinstance(event, dict):
            return None

        now = float(event.get('time', self._agent.sim.time))
        self._advance(now)
        self.event_count += 1

        reason = event.get('reason')
        if isinstance(reason, str):
            self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1

        change_type = event.get('change_type')
        if change_type == 'state':
            self.state_event_count += 1
            state = event.get('state')
            if isinstance(state, str):
                self._current_state = state
                self._state_time.setdefault(state, 0.0)
                self.state_entry_counts[state] = self.state_entry_counts.get(state, 0) + 1
        else:
            self.action_event_count += 1
        return None

    def stats(self) -> Dict[str, Any]:
        if self._agent is not None:
            now = float(self._agent.sim.time)
            self._advance(now)
        else:
            now = self._last_time
        duration = now - self._start_time
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': duration,
            'event_count': self.event_count,
            'state_event_count': self.state_event_count,
            'action_event_count': self.action_event_count,
            'current_state': self._current_state,
            'state_time': dict(self._state_time),
            'state_entry_counts': dict(self.state_entry_counts),
            'reason_counts': dict(self.reason_counts),
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class AgentProbeMixin:
    '''DSAgent probe extension mixin.

    Agent core behavior stays probe-agnostic; probes observe agent.tx_changed.
    '''

    def add_probe(self, probe: Any, name: Optional[str] = None) -> Any:
        if not hasattr(probe, 'attach'):
            raise ValueError(f'Probe {probe} must implement attach(agent).')
        if isinstance(probe, DSComponent):
            if probe.sim is not self.sim:
                raise ValueError('Probe component must belong to the same simulation instance as the agent.')
            if name is not None:
                expected_name = f'{self.name}.{name}'
                if probe.name != expected_name:
                    raise ValueError(f'Probe component name must be {expected_name}, got {probe.name}.')
        else:
            specific_name = name if name is not None else probe.__class__.__name__.lower()
            probe.name = f'{self.name}.{specific_name}'
        probe.attach(self)
        refs: List[Any] = getattr(self, '_probe_refs', [])
        refs.append(probe)
        self._probe_refs = refs
        return probe

    def remove_probe(self, probe: Any) -> None:
        refs: List[Any] = getattr(self, '_probe_refs', [])
        if probe in refs:
            refs.remove(probe)
            if hasattr(probe, 'close'):
                probe.close()
        self._probe_refs = refs

    def add_history_probe(self, enabled: bool = True, name: str = 'history_probe', max_events: Optional[int] = None) -> AgentHistoryProbe:
        probe = AgentHistoryProbe(
            enabled=enabled,
            max_events=max_events,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)

    def add_stats_probe(self, enabled: bool = True, name: str = 'stats_probe') -> AgentStatsProbe:
        probe = AgentStatsProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
