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
Resource probes implemented via pubsub endpoint observation (PRE phase).

This module intentionally keeps resource probing logic out of Resource core methods.
'''
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from dssim.base import DSComponent
from dssim.pubsub.pubsub import DSPub, DSCallback

if TYPE_CHECKING:
    from dssim.pubsub.components.resource import Resource
    from dssim.simulation import DSSimulation


class ResourceStatsProbe(DSComponent):
    '''Resource amount/flow probe using pubsub endpoint observation.

    Scope: tracks user-facing resource activity (put/get operation counts and
    amount over time) from resource endpoints.

    Non-goal: it does not monitor arbitrary custom waiting conditions (e.g.
    ``sim.gwait(custom_lambda)`` paths) or generic internal pubsub routing
    statistics. Such telemetry can be added separately.
    '''

    def __init__(self, enabled: bool = True, name: str = 'stats_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._resource: Optional['Resource'] = None
        self._pre_cb: Optional[DSCallback] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._last_amount: float = 0.0
        self._area_amount: float = 0.0
        self._area_nonempty: float = 0.0
        self._area_full: float = 0.0
        self.put_count: int = 0
        self.get_count: int = 0
        self.max_amount: float = 0.0
        self.min_amount: float = 0.0

    def attach(self, resource: 'Resource') -> None:
        self._resource = resource
        self._pre_cb = DSCallback(self._on_pre, sim=resource.sim)

        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.add_subscriber(self._pre_cb, phase.PRE)
        self.reset()

    def close(self) -> None:
        resource = self._resource
        if resource is None:
            return
        if self._pre_cb is None:
            self._resource = None
            return
        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.remove_subscriber(self._pre_cb, phase.PRE)
        self._resource = None

    def reset(self) -> None:
        if self._resource is None:
            self._start_time = 0.0
            self._last_time = 0.0
            self._last_amount = 0.0
            self.max_amount = 0.0
            self.min_amount = 0.0
        else:
            now = float(self._resource.sim.time)
            amount = float(self._resource.amount)
            self._start_time = now
            self._last_time = now
            self._last_amount = amount
            self.max_amount = amount
            self.min_amount = amount
        self._area_amount = 0.0
        self._area_nonempty = 0.0
        self._area_full = 0.0
        self.put_count = 0
        self.get_count = 0

    def _advance(self, now: float) -> None:
        dt = now - self._last_time
        if dt <= 0:
            return
        self._area_amount += dt * self._last_amount
        if self._last_amount > 0:
            self._area_nonempty += dt
        if self._resource is not None and self._resource.capacity != float('inf') and self._last_amount >= self._resource.capacity:
            self._area_full += dt
        self._last_time = now

    def _on_pre(self, event: Any) -> None:
        if not self.enabled or self._resource is None:
            return
        now = float(self._resource.sim.time)
        self._advance(now)
        current_amount = float(self._resource.amount)
        if event is self._resource.tx_nempty:
            self.put_count += 1
        elif event is self._resource.tx_nfull:
            self.get_count += 1
        self._last_amount = current_amount
        if current_amount > self.max_amount:
            self.max_amount = current_amount
        if current_amount < self.min_amount:
            self.min_amount = current_amount

    def stats(self) -> Dict[str, Any]:
        if self._resource is None:
            return {
                'start_time': self._start_time,
                'end_time': self._last_time,
                'duration': 0.0,
                'time_avg_amount': 0.0,
                'max_amount': self.max_amount,
                'min_amount': self.min_amount,
                'time_nonempty_ratio': 0.0,
                'time_full_ratio': 0.0,
                'put_count': self.put_count,
                'get_count': self.get_count,
                'current_amount': self._last_amount,
            }
        now = float(self._resource.sim.time)
        self._advance(now)
        duration = now - self._start_time
        if duration <= 0:
            avg_amount = self._last_amount
            nonempty_ratio = 1.0 if self._last_amount > 0 else 0.0
            full_ratio = 1.0 if self._resource.capacity != float('inf') and self._last_amount >= self._resource.capacity else 0.0
        else:
            avg_amount = self._area_amount / duration
            nonempty_ratio = self._area_nonempty / duration
            full_ratio = self._area_full / duration
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': duration,
            'time_avg_amount': avg_amount,
            'max_amount': self.max_amount,
            'min_amount': self.min_amount,
            'time_nonempty_ratio': nonempty_ratio,
            'time_full_ratio': full_ratio,
            'put_count': self.put_count,
            'get_count': self.get_count,
            'current_amount': self._last_amount,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class ResourceProbeMixin:
    '''Resource probe extension mixin.

    Resource core logic stays probe-agnostic; probes observe resource publishers.
    '''

    def add_probe(self, probe: Any, name: Optional[str] = None) -> Any:
        if not hasattr(probe, 'attach'):
            raise ValueError(f'Probe {probe} must implement attach(resource).')
        if isinstance(probe, DSComponent):
            if probe.sim is not self.sim:
                raise ValueError('Probe component must belong to the same simulation instance as the resource.')
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

    def add_stats_probe(self, enabled: bool = True, name: str = 'stats_probe') -> ResourceStatsProbe:
        probe = ResourceStatsProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
