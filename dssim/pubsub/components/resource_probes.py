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
DSResource probes implemented via pubsub endpoint observation (PRE phase).

This module intentionally keeps resource probing logic out of DSResource core methods.
'''
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from dssim.base import DSComponent
from dssim.pubsub.pubsub import DSPub, DSSub

if TYPE_CHECKING:
    from dssim.pubsub.components.resource import DSResource
    from dssim.simulation import DSSimulation


class ResourceStatsProbe(DSSub):
    '''DSResource amount/flow probe using pubsub endpoint observation.

    Scope: tracks user-facing resource activity (put/get operation counts and
    amount over time) from resource endpoints.

    Non-goal: it does not monitor arbitrary custom waiting conditions (e.g.
    ``sim.gwait(custom_lambda)`` paths) or generic internal pubsub routing
    statistics. Such telemetry can be added separately.
    '''

    def __init__(self, enabled: bool = True, name: str = 'stats_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._resource: Optional['DSResource'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._last_amount: float = 0.0
        self._area_amount: float = 0.0
        self._area_nonempty: float = 0.0
        self._area_full: float = 0.0
        self._base_preempt_count: int = 0
        self._base_preempted_amount: float = 0.0
        self.put_count: int = 0
        self.get_count: int = 0
        self.max_amount: float = 0.0
        self.min_amount: float = 0.0

    def attach(self, resource: 'DSResource') -> None:
        self._resource = resource

        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.add_subscriber(self, phase.PRE)
        self.reset()

    def close(self) -> None:
        resource = self._resource
        if resource is None:
            return
        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.remove_subscriber(self, phase.PRE)
        self._resource = None

    def reset(self) -> None:
        if self._resource is None:
            self._start_time = 0.0
            self._last_time = 0.0
            self._last_amount = 0.0
            self.max_amount = 0.0
            self.min_amount = 0.0
            self._base_preempt_count = 0
            self._base_preempted_amount = 0.0
        else:
            now = float(self._resource.sim.time)
            amount = float(self._resource.amount)
            self._start_time = now
            self._last_time = now
            self._last_amount = amount
            self.max_amount = amount
            self.min_amount = amount
            self._base_preempt_count = int(getattr(self._resource, 'preempt_count', 0))
            self._base_preempted_amount = float(getattr(self._resource, 'preempted_amount', 0.0))
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

    def send(self, event: Any) -> None:
        if not self.enabled or self._resource is None:
            return None
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
        return None

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
                'preempt_count': 0,
                'preempted_amount': 0.0,
                'current_amount': self._last_amount,
            }
        now = float(self._resource.sim.time)
        self._advance(now)
        duration = now - self._start_time
        preempt_count = int(getattr(self._resource, 'preempt_count', 0)) - self._base_preempt_count
        preempted_amount = float(getattr(self._resource, 'preempted_amount', 0.0)) - self._base_preempted_amount
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
            'preempt_count': preempt_count,
            'preempted_amount': preempted_amount,
            'current_amount': self._last_amount,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class ResourceFlowProbe(DSSub):
    '''DSResource transfer probe focused on moved amounts and rates.

    Observes only successful transfer endpoints:
    - tx_nempty: successful put-side amount increase
    - tx_nfull:  successful get-side amount decrease
    '''

    def __init__(self, enabled: bool = True, name: str = 'flow_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._resource: Optional['DSResource'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._last_amount: float = 0.0
        self.reset()

    def attach(self, resource: 'DSResource') -> None:
        self._resource = resource
        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.add_subscriber(self, phase.PRE)
        self.reset()

    def close(self) -> None:
        resource = self._resource
        if resource is None:
            return
        phase = DSPub.Phase
        for ep in (resource.tx_nempty, resource.tx_nfull):
            ep.remove_subscriber(self, phase.PRE)
        self._resource = None

    def reset(self) -> None:
        if self._resource is None:
            self._start_time = 0.0
            self._last_time = 0.0
            self._last_amount = 0.0
        else:
            now = float(self._resource.sim.time)
            self._start_time = now
            self._last_time = now
            self._last_amount = float(self._resource.amount)

        self.put_event_count = 0
        self.get_event_count = 0
        self.put_amount_total = 0.0
        self.get_amount_total = 0.0
        self.max_put_amount = 0.0
        self.max_get_amount = 0.0
        self.unexpected_nempty_count = 0
        self.unexpected_nfull_count = 0

    def send(self, event: Any) -> None:
        if not self.enabled or self._resource is None:
            return None

        now = float(self._resource.sim.time)
        self._last_time = now
        current_amount = float(self._resource.amount)
        delta = current_amount - self._last_amount

        if event is self._resource.tx_nempty:
            if delta > 0:
                self.put_event_count += 1
                self.put_amount_total += delta
                if delta > self.max_put_amount:
                    self.max_put_amount = delta
            else:
                self.unexpected_nempty_count += 1
        elif event is self._resource.tx_nfull:
            if delta < 0:
                moved = -delta
                self.get_event_count += 1
                self.get_amount_total += moved
                if moved > self.max_get_amount:
                    self.max_get_amount = moved
            else:
                self.unexpected_nfull_count += 1

        self._last_amount = current_amount
        return None

    def _avg(self, total: float, count: int) -> float:
        return total / count if count > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        if self._resource is not None:
            now = float(self._resource.sim.time)
            end_time = now
            duration = now - self._start_time
        else:
            end_time = self._last_time
            duration = 0.0
        if duration > 0:
            put_rate = self.put_amount_total / duration
            get_rate = self.get_amount_total / duration
        else:
            put_rate = 0.0
            get_rate = 0.0
        return {
            'start_time': self._start_time,
            'end_time': end_time,
            'duration': duration,
            'put_event_count': self.put_event_count,
            'get_event_count': self.get_event_count,
            'put_amount_total': self.put_amount_total,
            'get_amount_total': self.get_amount_total,
            'net_amount_total': self.put_amount_total - self.get_amount_total,
            'avg_put_amount': self._avg(self.put_amount_total, self.put_event_count),
            'avg_get_amount': self._avg(self.get_amount_total, self.get_event_count),
            'max_put_amount': self.max_put_amount,
            'max_get_amount': self.max_get_amount,
            'put_rate': put_rate,
            'get_rate': get_rate,
            'unexpected_nempty_count': self.unexpected_nempty_count,
            'unexpected_nfull_count': self.unexpected_nfull_count,
            'current_amount': self._last_amount,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class ResourceLatencyProbe(DSSub):
    '''DSResource latency probe for wait-time statistics.

    Tracks blocked wait durations for put/get operations using tx_ops events.
    '''

    def __init__(self, enabled: bool = True, name: str = 'latency_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._resource: Optional['DSResource'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self.reset()

    def attach(self, resource: 'DSResource') -> None:
        self._resource = resource
        phase = DSPub.Phase
        resource.tx_ops.add_subscriber(self, phase.PRE)
        self.reset()

    def close(self) -> None:
        resource = self._resource
        if resource is None:
            return
        phase = DSPub.Phase
        resource.tx_ops.remove_subscriber(self, phase.PRE)
        self._resource = None

    def _accumulate(self, prefix: str, value: float) -> None:
        count_name = f'{prefix}_count'
        total_name = f'{prefix}_time_total'
        min_name = f'{prefix}_time_min'
        max_name = f'{prefix}_time_max'
        setattr(self, count_name, getattr(self, count_name) + 1)
        setattr(self, total_name, getattr(self, total_name) + value)
        if value < getattr(self, min_name):
            setattr(self, min_name, value)
        if value > getattr(self, max_name):
            setattr(self, max_name, value)

    def reset(self) -> None:
        now = float(self._resource.sim.time) if self._resource is not None else 0.0
        self._start_time = now
        self._last_time = now

        self.put_wait_count = 0
        self.put_wait_timeout_count = 0
        self.put_wait_time_total = 0.0
        self.put_wait_time_min = float('inf')
        self.put_wait_time_max = 0.0

        self.get_wait_count = 0
        self.get_wait_timeout_count = 0
        self.get_wait_time_total = 0.0
        self.get_wait_time_min = float('inf')
        self.get_wait_time_max = 0.0

    def send(self, event: Any) -> None:
        if not self.enabled or self._resource is None:
            return None
        if not isinstance(event, dict) or event.get('kind') != 'resource_op':
            return None

        now = float(event.get('time', self._resource.sim.time))
        self._last_time = now
        op = event.get('op')
        blocked = bool(event.get('blocked', False))
        timeout = bool(event.get('timeout', False))
        wait_time = float(event.get('wait_time', 0.0))

        if op == 'put' and blocked:
            self._accumulate('put_wait', wait_time)
            if timeout:
                self.put_wait_timeout_count += 1
        elif op == 'get' and blocked:
            self._accumulate('get_wait', wait_time)
            if timeout:
                self.get_wait_timeout_count += 1
        return None

    def _avg(self, total: float, count: int) -> float:
        return total / count if count > 0 else 0.0

    def _min_or_zero(self, value: float, count: int) -> float:
        return value if count > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        if self._resource is not None:
            now = float(self._resource.sim.time)
            end_time = now
            duration = now - self._start_time
        else:
            end_time = self._last_time
            duration = 0.0
        return {
            'start_time': self._start_time,
            'end_time': end_time,
            'duration': duration,
            'put_wait_count': self.put_wait_count,
            'put_wait_timeout_count': self.put_wait_timeout_count,
            'put_wait_time_total': self.put_wait_time_total,
            'put_wait_time_avg': self._avg(self.put_wait_time_total, self.put_wait_count),
            'put_wait_time_min': self._min_or_zero(self.put_wait_time_min, self.put_wait_count),
            'put_wait_time_max': self.put_wait_time_max,
            'get_wait_count': self.get_wait_count,
            'get_wait_timeout_count': self.get_wait_timeout_count,
            'get_wait_time_total': self.get_wait_time_total,
            'get_wait_time_avg': self._avg(self.get_wait_time_total, self.get_wait_count),
            'get_wait_time_min': self._min_or_zero(self.get_wait_time_min, self.get_wait_count),
            'get_wait_time_max': self.get_wait_time_max,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class ResourceProbeMixin:
    '''DSResource probe extension mixin.

    DSResource core logic stays probe-agnostic; probes observe resource publishers.
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

    def add_flow_probe(self, enabled: bool = True, name: str = 'flow_probe') -> ResourceFlowProbe:
        probe = ResourceFlowProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)

    def add_latency_probe(self, enabled: bool = True, name: str = 'latency_probe') -> ResourceLatencyProbe:
        probe = ResourceLatencyProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
