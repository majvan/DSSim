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
DSQueue probes implemented via pubsub observers (PRE phase).

This module intentionally keeps queue probing logic out of DSQueue core methods.
'''
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from dssim.base import DSComponent
from dssim.pubsub.pubsub import DSPub, DSSub

if TYPE_CHECKING:
    from dssim.pubsub.components.queue import DSQueue
    from dssim.simulation import DSSimulation


class QueueStatsProbe(DSSub):
    '''DSQueue occupancy/flow probe using pubsub endpoint observation.

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
        self._queue: Optional['DSQueue'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._last_len: int = 0
        self._area_len: float = 0.0
        self._area_nonempty: float = 0.0
        self.put_count: int = 0
        self.get_count: int = 0
        self.max_len: int = 0

    def attach(self, queue: 'DSQueue') -> None:
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


class QueueOpsProbe(DSSub):
    '''DSQueue operation probe using queue operation events.

    Tracks API-level queue operation attempts, outcomes and transferred item
    counts. Intended as a complement to QueueStatsProbe, not a replacement.
    '''

    def __init__(self, enabled: bool = True, name: str = 'ops_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._queue: Optional['DSQueue'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self.current_len: int = 0
        self.max_len: int = 0
        self.min_len: int = 0
        self.reset()

    def attach(self, queue: 'DSQueue') -> None:
        self._queue = queue
        Phase = DSPub.Phase
        queue.tx_ops.add_subscriber(self, Phase.PRE)
        self.reset()

    def close(self) -> None:
        queue = self._queue
        if queue is None:
            return
        Phase = DSPub.Phase
        queue.tx_ops.remove_subscriber(self, Phase.PRE)
        self._queue = None

    def reset(self) -> None:
        now = float(self._queue.sim.time) if self._queue is not None else 0.0
        current_len = len(self._queue) if self._queue is not None else 0
        self._start_time = now
        self._last_time = now
        self.current_len = current_len
        self.max_len = current_len
        self.min_len = current_len

        self.put_attempt_count = 0
        self.put_success_count = 0
        self.put_fail_count = 0
        self.put_blocked_count = 0
        self.put_timeout_count = 0
        self.put_requested_items = 0
        self.put_moved_items = 0

        self.get_attempt_count = 0
        self.get_success_count = 0
        self.get_fail_count = 0
        self.get_blocked_count = 0
        self.get_timeout_count = 0
        self.get_requested_items = 0
        self.get_moved_items = 0

        self.pop_attempt_count = 0
        self.pop_success_count = 0
        self.pop_fail_count = 0
        self.pop_moved_items = 0

        self.remove_attempt_count = 0
        self.remove_success_count = 0
        self.remove_fail_count = 0
        self.remove_moved_items = 0

        self.setitem_count = 0

        self.max_put_batch = 0
        self.max_get_batch = 0

    def _inc_queue_len_extrema(self, queue_len: int) -> None:
        self.current_len = queue_len
        if queue_len > self.max_len:
            self.max_len = queue_len
        if queue_len < self.min_len:
            self.min_len = queue_len

    def send(self, event: Any) -> None:
        if not self.enabled or self._queue is None:
            return None
        if not isinstance(event, dict) or event.get('kind') != 'queue_op':
            return None
        now = float(self._queue.sim.time)
        self._last_time = now

        op = event.get('op')
        requested = int(event.get('requested', 0))
        moved = int(event.get('moved', 0))
        success = bool(event.get('success', False))
        blocked = bool(event.get('blocked', False))
        timeout = bool(event.get('timeout', False))
        queue_len = int(event.get('queue_len', len(self._queue)))
        self._inc_queue_len_extrema(queue_len)

        if op == 'put':
            self.put_attempt_count += 1
            self.put_requested_items += requested
            self.put_moved_items += moved
            if blocked:
                self.put_blocked_count += 1
            if timeout:
                self.put_timeout_count += 1
            if success:
                self.put_success_count += 1
                if moved > self.max_put_batch:
                    self.max_put_batch = moved
            else:
                self.put_fail_count += 1
        elif op == 'get':
            self.get_attempt_count += 1
            self.get_requested_items += requested
            self.get_moved_items += moved
            if blocked:
                self.get_blocked_count += 1
            if timeout:
                self.get_timeout_count += 1
            if success:
                self.get_success_count += 1
                if moved > self.max_get_batch:
                    self.max_get_batch = moved
            else:
                self.get_fail_count += 1
        elif op == 'pop':
            self.pop_attempt_count += 1
            self.pop_moved_items += moved
            if success:
                self.pop_success_count += 1
            else:
                self.pop_fail_count += 1
        elif op == 'remove':
            self.remove_attempt_count += 1
            self.remove_moved_items += moved
            if success:
                self.remove_success_count += 1
            else:
                self.remove_fail_count += 1
        elif op == 'setitem':
            self.setitem_count += 1
        return None

    def stats(self) -> Dict[str, Any]:
        duration = self._last_time - self._start_time if self._queue is not None else 0.0
        return {
            'start_time': self._start_time,
            'end_time': self._last_time,
            'duration': duration,
            'current_len': self.current_len,
            'max_len': self.max_len,
            'min_len': self.min_len,
            'put_attempt_count': self.put_attempt_count,
            'put_success_count': self.put_success_count,
            'put_fail_count': self.put_fail_count,
            'put_blocked_count': self.put_blocked_count,
            'put_timeout_count': self.put_timeout_count,
            'put_requested_items': self.put_requested_items,
            'put_moved_items': self.put_moved_items,
            'get_attempt_count': self.get_attempt_count,
            'get_success_count': self.get_success_count,
            'get_fail_count': self.get_fail_count,
            'get_blocked_count': self.get_blocked_count,
            'get_timeout_count': self.get_timeout_count,
            'get_requested_items': self.get_requested_items,
            'get_moved_items': self.get_moved_items,
            'pop_attempt_count': self.pop_attempt_count,
            'pop_success_count': self.pop_success_count,
            'pop_fail_count': self.pop_fail_count,
            'pop_moved_items': self.pop_moved_items,
            'remove_attempt_count': self.remove_attempt_count,
            'remove_success_count': self.remove_success_count,
            'remove_fail_count': self.remove_fail_count,
            'remove_moved_items': self.remove_moved_items,
            'setitem_count': self.setitem_count,
            'max_put_batch': self.max_put_batch,
            'max_get_batch': self.max_get_batch,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class QueueLatencyProbe(DSSub):
    '''DSQueue latency probe for stay-time and wait-time statistics.

    - stay-time: item time inside queue (enqueue -> dequeue/pop/remove/setitem-out)
    - wait-time: blocked wait duration for put/get style operations
    '''

    def __init__(self, enabled: bool = True, name: str = 'latency_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._queue: Optional['DSQueue'] = None
        self._start_time: float = 0.0
        self._last_time: float = 0.0
        self._item_enter_timestamps: Dict[int, deque[float]] = {}
        self.reset()

    def attach(self, queue: 'DSQueue') -> None:
        self._queue = queue
        Phase = DSPub.Phase
        queue.tx_ops.add_subscriber(self, Phase.PRE)
        self.reset()

    def close(self) -> None:
        queue = self._queue
        if queue is None:
            return
        Phase = DSPub.Phase
        queue.tx_ops.remove_subscriber(self, Phase.PRE)
        self._queue = None

    def _seed_existing_items(self) -> None:
        if self._queue is None:
            return
        now = float(self._queue.sim.time)
        for item in self._queue:
            key = id(item)
            self._item_enter_timestamps.setdefault(key, deque()).append(now)
            self.seeded_item_count += 1

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

    def _consume_item_exit(self, item: Any, now: float) -> None:
        key = id(item)
        q = self._item_enter_timestamps.get(key)
        if q is None or not q:
            self.untracked_exit_count += 1
            return
        t_in = q.popleft()
        if not q:
            self._item_enter_timestamps.pop(key, None)
        self._accumulate('stay', now - t_in)

    def reset(self) -> None:
        now = float(self._queue.sim.time) if self._queue is not None else 0.0
        self._start_time = now
        self._last_time = now
        self._item_enter_timestamps = {}
        self.seeded_item_count = 0
        self.untracked_exit_count = 0

        self.stay_count = 0
        self.stay_time_total = 0.0
        self.stay_time_min = float('inf')
        self.stay_time_max = 0.0

        self.put_wait_count = 0
        self.put_wait_time_total = 0.0
        self.put_wait_time_min = float('inf')
        self.put_wait_time_max = 0.0
        self.put_wait_timeout_count = 0

        self.get_wait_count = 0
        self.get_wait_time_total = 0.0
        self.get_wait_time_min = float('inf')
        self.get_wait_time_max = 0.0
        self.get_wait_timeout_count = 0

        self._seed_existing_items()

    def send(self, event: Any) -> None:
        if not self.enabled or self._queue is None:
            return None
        if not isinstance(event, dict) or event.get('kind') != 'queue_op':
            return None

        now = float(event.get('time', self._queue.sim.time))
        self._last_time = now
        op = event.get('op')
        blocked = bool(event.get('blocked', False))
        timeout = bool(event.get('timeout', False))
        wait_time = float(event.get('wait_time', 0.0))
        items_in = event.get('items_in', ())
        items_out = event.get('items_out', ())

        if op == 'put':
            if blocked:
                self._accumulate('put_wait', wait_time)
                if timeout:
                    self.put_wait_timeout_count += 1
            for item in items_in:
                key = id(item)
                self._item_enter_timestamps.setdefault(key, deque()).append(now)
        elif op == 'get':
            if blocked:
                self._accumulate('get_wait', wait_time)
                if timeout:
                    self.get_wait_timeout_count += 1
            for item in items_out:
                self._consume_item_exit(item, now)
        elif op in ('pop', 'remove', 'setitem'):
            for item in items_out:
                self._consume_item_exit(item, now)
            for item in items_in:
                key = id(item)
                self._item_enter_timestamps.setdefault(key, deque()).append(now)
        return None

    def _avg(self, total: float, count: int) -> float:
        return total / count if count > 0 else 0.0

    def _min_or_zero(self, value: float, count: int) -> float:
        return value if count > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        tracked_item_count = sum(len(v) for v in self._item_enter_timestamps.values())
        duration = self._last_time - self._start_time
        return {
            'start_time': self._start_time,
            'end_time': self._last_time,
            'duration': duration,
            'tracked_item_count': tracked_item_count,
            'seeded_item_count': self.seeded_item_count,
            'untracked_exit_count': self.untracked_exit_count,
            'stay_count': self.stay_count,
            'stay_time_total': self.stay_time_total,
            'stay_time_avg': self._avg(self.stay_time_total, self.stay_count),
            'stay_time_min': self._min_or_zero(self.stay_time_min, self.stay_count),
            'stay_time_max': self.stay_time_max,
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


class QueueProbeMixin:
    '''DSQueue probe extension mixin.

    DSQueue core logic stays probe-agnostic; probes observe queue publishers.
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

    def add_ops_probe(self, enabled: bool = True, name: str = 'ops_probe') -> QueueOpsProbe:
        probe = QueueOpsProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)

    def add_latency_probe(self, enabled: bool = True, name: str = 'latency_probe') -> QueueLatencyProbe:
        probe = QueueLatencyProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
