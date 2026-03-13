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
Queue probes implemented via pubsub observers (PRE phase).

This module intentionally keeps queue probing logic out of Queue core methods.
'''
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from dssim.base import DSComponent
from dssim.pubsub.pubsub import DSPub, DSSub

if TYPE_CHECKING:
    from dssim.pubsub.components.queue import Queue
    from dssim.simulation import DSSimulation


class QueueStatsProbe(DSSub):
    '''Queue occupancy/flow probe using pubsub endpoint observation.

    Scope: this probe tracks user-facing queue activity (puts/gets and
    occupancy over time) from queue endpoints.

    Non-goal: it does not monitor out-of-control custom waiting conditions
    (e.g. arbitrary ``sim.gwait(custom_lambda)`` paths) or generic internal
    pubsub routing statistics. Such monitoring can be added later as a
    separate component dedicated to internal pubsub telemetry.
    '''

    def __init__(self, enabled: bool = True, name: str = 'stats_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._queue: Optional['Queue'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._last_len: int = 0
        self._area_len: float = 0.0
        self._area_nonempty: float = 0.0
        self.put_count: int = 0
        self.get_count: int = 0
        self.max_len: int = 0

    def attach(self, queue: 'Queue') -> None:
        self._queue = queue

        Phase = DSPub.Phase
        for ep in (queue.tx_nempty, queue.tx_nfull):
            ep.add_subscriber(self, Phase.PRE)
        self.reset()

    def close(self) -> None:
        queue = self._queue
        if queue is None:
            return
        Phase = DSPub.Phase
        for ep in (queue.tx_nempty, queue.tx_nfull):
            ep.remove_subscriber(self, Phase.PRE)
        self._queue = None

    def reset(self) -> None:
        if self._queue is None:
            self._start_time = 0.0
            self._last_time = 0.0
            self._last_len = 0
            self.max_len = 0
        else:
            now = float(self._queue.sim.time)
            self._start_time = now
            self._last_time = now
            self._last_len = len(self._queue)
            self.max_len = self._last_len
        self._area_len = 0.0
        self._area_nonempty = 0.0
        self.put_count = 0
        self.get_count = 0

    def _advance(self, now: float) -> None:
        dt = now - self._last_time
        if dt <= 0:
            return
        self._area_len += dt * self._last_len
        if self._last_len > 0:
            self._area_nonempty += dt
        self._last_time = now

    def send(self, event: Any) -> None:
        if not self.enabled or self._queue is None:
            return None
        now = float(self._queue.sim.time)
        self._advance(now)
        current_len = len(self._queue)
        if event is self._queue.tx_nempty:
            self.put_count += 1
        elif event is self._queue.tx_nfull:
            self.get_count += 1
        self._last_len = current_len
        if current_len > self.max_len:
            self.max_len = current_len
        return None

    def stats(self) -> Dict[str, Any]:
        if self._queue is None:
            return {
                'start_time': self._start_time,
                'end_time': self._last_time,
                'duration': 0.0,
                'time_avg_len': 0.0,
                'max_len': self.max_len,
                'time_nonempty_ratio': 0.0,
                'put_count': self.put_count,
                'get_count': self.get_count,
                'current_len': self._last_len,
            }
        now = float(self._queue.sim.time)
        self._advance(now)
        duration = now - self._start_time
        if duration <= 0:
            avg_len = float(self._last_len)
            nonempty_ratio = 1.0 if self._last_len > 0 else 0.0
        else:
            avg_len = self._area_len / duration
            nonempty_ratio = self._area_nonempty / duration
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': duration,
            'time_avg_len': avg_len,
            'max_len': self.max_len,
            'time_nonempty_ratio': nonempty_ratio,
            'put_count': self.put_count,
            'get_count': self.get_count,
            'current_len': self._last_len,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class QueueProbeMixin:
    '''Queue probe extension mixin.

    Queue core logic stays probe-agnostic; probes observe queue publishers.
    '''

    def add_probe(self, probe: Any, name: Optional[str] = None) -> Any:
        if not hasattr(probe, 'attach'):
            raise ValueError(f'Probe {probe} must implement attach(queue).')
        if isinstance(probe, DSComponent):
            if probe.sim is not self.sim:
                raise ValueError('Probe component must belong to the same simulation instance as the queue.')
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

    def add_stats_probe(self, enabled: bool = True, name: str = 'stats_probe') -> QueueStatsProbe:
        probe = QueueStatsProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
