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


class AgentActivityProbe(DSSub):
    '''Attribute simulated time to the activity an agent was performing.

    Observes ``agent.tx_changed`` only. Each *blocking* action event (``hold``,
    ``passivate``, ``wait``/``gwait``, ``get*``/``put*``, ``enter``/``pop``) is emitted
    when the blocking call returns, so the interval since the agent's previous transition
    is the time it spent in that activity. Instantaneous actions (``activate``,
    ``*_nowait``, ``leave``) are counted but consume no simulated time.

    From the result a caller can read, per agent, how long it spent holding / passivated /
    waiting / requesting, and — via ``time_by_resource`` / ``time_by_container`` — how long
    it waited on a specific resource or container.
    '''

    # Action verbs that block, i.e. whose event marks the end of a time-consuming wait.
    BLOCKING = frozenset({
        'hold', 'passivate', 'wait', 'gwait',
        'enter', 'genter', 'pop', 'gpop',
        'enter_abort', 'genter_abort', 'pop_abort', 'gpop_abort',
        'get', 'gget', 'get_n', 'gget_n',
        'put', 'gput', 'put_n', 'gput_n',
    })

    def __init__(self, enabled: bool = True, name: str = 'activity_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._agent: Optional['DSAgent'] = None
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
        self._mark = now
        self._finished = False
        self.time_by_activity: Dict[str, float] = {}
        self.count_by_activity: Dict[str, int] = {}
        self.time_by_resource: Dict[str, float] = {}
        self.time_by_container: Dict[str, float] = {}
        self.pending_time = 0.0

    @staticmethod
    def _target_name(target: Any) -> str:
        return getattr(target, 'name', None) or repr(target)

    def send(self, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return None
        if not isinstance(event, dict):
            return None

        now = float(event.get('time', self._agent.sim.time))
        reason = event.get('reason')
        details = event.get('details') or {}

        if event.get('change_type') == 'state':
            # The process ending closes the lifetime; any residual is an unattributed gap
            # (e.g. a hold/wait aborted without emitting its own action event).
            if event.get('state') in ('finished', 'failed'):
                self.pending_time += max(0.0, now - self._mark)
                self._mark = now
                self._finished = True
            return None

        if isinstance(reason, str):
            self.count_by_activity[reason] = self.count_by_activity.get(reason, 0) + 1

        if reason in self.BLOCKING:
            dt = now - self._mark
            if dt > 0:
                self.time_by_activity[reason] = self.time_by_activity.get(reason, 0.0) + dt
                resource = details.get('resource')
                if resource is not None:
                    rname = self._target_name(resource)
                    self.time_by_resource[rname] = self.time_by_resource.get(rname, 0.0) + dt
                container = details.get('container')
                if container is not None:
                    cname = self._target_name(container)
                    self.time_by_container[cname] = self.time_by_container.get(cname, 0.0) + dt
            self._mark = now
        return None

    def time_in(self, activity: str) -> float:
        '''Total simulated time the agent spent in `activity` (e.g. 'passivate', 'gwait').'''
        return self.time_by_activity.get(activity, 0.0)

    def time_waiting_for(self, target: Any) -> float:
        '''Total time the agent blocked on `target` (a resource/container or its name).'''
        name = target if isinstance(target, str) else self._target_name(target)
        if name in self.time_by_resource:
            return self.time_by_resource[name]
        return self.time_by_container.get(name, 0.0)

    def stats(self) -> Dict[str, Any]:
        now = float(self._agent.sim.time) if self._agent is not None else self._mark
        pending = self.pending_time
        if not self._finished:
            pending += max(0.0, now - self._mark)
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': now - self._start_time,
            'time_by_activity': dict(self.time_by_activity),
            'count_by_activity': dict(self.count_by_activity),
            'time_by_resource': dict(self.time_by_resource),
            'time_by_container': dict(self.time_by_container),
            'pending_time': pending,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class _TargetOpsWatch:
    '''PRE-phase tx_ops subscriber binding one component to an agent probe.

    A tx_ops event does not carry a reference to its emitting component, so a
    probe subscribes one watch per component to restore that context.
    '''

    supports_direct_send = True

    def __init__(self, probe: Any, target: Any) -> None:
        self.probe = probe
        self.target = target

    def send(self, event: Any) -> None:
        self.probe._on_target_op(self.target, event)
        return None


class AgentQueueingProbe(DSSub):
    '''Measure the true time an agent spends inside containers it entered.

    Observes ``agent.tx_changed`` for successful ``enter``/``genter``/``enter_nowait``
    events; each carries the container in its details. The probe then subscribes to
    that container's ``tx_ops`` publisher and closes the interval when the agent
    appears in ``items_out`` of any removal operation (``get``/``pop``/``remove``/
    ``setitem``) — including removals performed by other processes, which the agent
    itself never observes. Containers stay agent-agnostic; only containers exposing
    ``tx_ops`` (e.g. DSQueue) are observable — entries into others are counted in
    ``unobservable_enter_count``.

    Entries made by third parties (someone else putting this agent into a queue)
    are not tracked; their removals are counted in ``untracked_exit_count``.
    '''

    def __init__(self, enabled: bool = True, name: str = 'queueing_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._agent: Optional['DSAgent'] = None
        self._watches: Dict[int, _TargetOpsWatch] = {}
        self._entries: Dict[int, Deque[float]] = {}
        self.reset()

    def attach(self, agent: 'DSAgent') -> None:
        self._agent = agent
        agent.tx_changed.add_subscriber(self, DSPub.Phase.PRE)
        self.reset()

    def close(self) -> None:
        agent = self._agent
        if agent is None:
            return
        self._release_watches()
        agent.tx_changed.remove_subscriber(self, DSPub.Phase.PRE)
        self._agent = None

    def _release_watches(self) -> None:
        for watch in self._watches.values():
            watch.target.tx_ops.remove_subscriber(watch, DSPub.Phase.PRE)
        self._watches = {}
        self._entries = {}

    def reset(self) -> None:
        self._release_watches()
        now = float(self._agent.sim.time) if self._agent is not None else 0.0
        self._start_time = now

        self.stay_count = 0
        self.stay_time_total = 0.0
        self.stay_time_min = float('inf')
        self.stay_time_max = 0.0
        self.time_by_container: Dict[str, float] = {}
        self.count_by_container: Dict[str, int] = {}
        self.unobservable_enter_count = 0
        self.untracked_exit_count = 0

    @staticmethod
    def _target_name(target: Any) -> str:
        return getattr(target, 'name', None) or repr(target)

    def _account_stay(self, container: Any, value: float) -> None:
        self.stay_count += 1
        self.stay_time_total += value
        if value < self.stay_time_min:
            self.stay_time_min = value
        if value > self.stay_time_max:
            self.stay_time_max = value
        cname = self._target_name(container)
        self.time_by_container[cname] = self.time_by_container.get(cname, 0.0) + value
        self.count_by_container[cname] = self.count_by_container.get(cname, 0) + 1

    def _maybe_release(self, key: int) -> None:
        if self._entries.get(key):
            return
        self._entries.pop(key, None)
        watch = self._watches.pop(key, None)
        if watch is not None:
            watch.target.tx_ops.remove_subscriber(watch, DSPub.Phase.PRE)

    def _track_entry(self, container: Any, now: float) -> None:
        tx_ops = getattr(container, 'tx_ops', None)
        if tx_ops is None:
            self.unobservable_enter_count += 1
            return
        key = id(container)
        if key not in self._watches:
            watch = _TargetOpsWatch(self, container)
            tx_ops.add_subscriber(watch, DSPub.Phase.PRE)
            self._watches[key] = watch
        # A consumer waiting on the container may have taken the agent in the same
        # instant, before this 'enter' event was dispatched (event delivery is
        # deferred through the now-queue); the exit op is then unobservable, but the
        # stay provably started and ended at the same simulation time.
        try:
            still_inside = self._agent in container
        except TypeError:
            still_inside = True
        if still_inside:
            self._entries.setdefault(key, deque()).append(now)
        else:
            self._account_stay(container, 0.0)
            self._maybe_release(key)

    def send(self, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return None
        if not isinstance(event, dict) or event.get('kind') != 'agent_state':
            return None
        if event.get('change_type') == 'state':
            return None
        if event.get('reason') not in ('enter', 'genter', 'enter_nowait'):
            return None
        details = event.get('details') or {}
        if not details.get('success'):
            return None
        container = details.get('container')
        if container is None:
            return None
        now = float(event.get('time', self._agent.sim.time))
        self._track_entry(container, now)
        return None

    def _on_target_op(self, container: Any, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return
        if not isinstance(event, dict) or event.get('kind') != 'queue_op':
            return
        agent = self._agent
        exits = sum(1 for item in event.get('items_out', ()) if item is agent)
        if exits == 0:
            return
        now = float(event.get('time', agent.sim.time))
        key = id(container)
        entries = self._entries.get(key)
        for _ in range(exits):
            if entries:
                t_in = entries.popleft()
                self._account_stay(container, now - t_in)
            else:
                self.untracked_exit_count += 1
        self._maybe_release(key)

    def time_in_queue(self, container: Any = None) -> float:
        '''Total completed stay time, overall or for a specific container (or its name).'''
        if container is None:
            return self.stay_time_total
        name = container if isinstance(container, str) else self._target_name(container)
        return self.time_by_container.get(name, 0.0)

    def stats(self) -> Dict[str, Any]:
        now = float(self._agent.sim.time) if self._agent is not None else self._start_time
        currently_queued = {
            self._target_name(watch.target): len(self._entries[key])
            for key, watch in self._watches.items() if self._entries.get(key)
        }
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': now - self._start_time,
            'stay_count': self.stay_count,
            'stay_time_total': self.stay_time_total,
            'stay_time_avg': self.stay_time_total / self.stay_count if self.stay_count > 0 else 0.0,
            'stay_time_min': self.stay_time_min if self.stay_count > 0 else 0.0,
            'stay_time_max': self.stay_time_max,
            'time_by_container': dict(self.time_by_container),
            'count_by_container': dict(self.count_by_container),
            'currently_queued': currently_queued,
            'unobservable_enter_count': self.unobservable_enter_count,
            'untracked_exit_count': self.untracked_exit_count,
        }

    def get_statistics(self) -> Dict[str, Any]:
        return self.stats()


class AgentResourceProbe(DSSub):
    '''Account the resource amounts an agent spends and holds.

    Observes ``agent.tx_changed`` only: the ``get*``/``put*`` action events from
    AgentResourceMixin carry the resource, the amount moved and the success flag.
    Per resource the probe tracks acquired/released totals, the running balance
    (acquired - released; negative means the agent is a net producer), the peak
    balance, and the time integral of the balance — so ``avg_held`` is the
    time-weighted average amount held over the observation window.

    Amounts reclaimed by preemption (DSPriorityResource with ``preempt=True``)
    bypass the holder's put APIs; to keep the balance honest the probe also
    subscribes to the ``tx_ops`` of every resource the agent touched and books
    ``preempt`` ops targeting this agent's process as ``preempted_total``,
    reducing the balance at the moment of the reclaim.
    '''

    GET_REASONS = frozenset({'get', 'gget', 'get_n', 'gget_n'})
    PUT_REASONS = frozenset({'put', 'gput', 'put_n', 'gput_n', 'put_nowait', 'put_n_nowait'})

    def __init__(self, enabled: bool = True, name: str = 'resource_probe', sim: Optional['DSSimulation'] = None) -> None:
        super().__init__(name=name, sim=sim)
        self.enabled = enabled
        self._agent: Optional['DSAgent'] = None
        self._watches: Dict[int, _TargetOpsWatch] = {}
        self.reset()

    def attach(self, agent: 'DSAgent') -> None:
        self._agent = agent
        agent.tx_changed.add_subscriber(self, DSPub.Phase.PRE)
        self.reset()

    def close(self) -> None:
        agent = self._agent
        if agent is None:
            return
        self._release_watches()
        agent.tx_changed.remove_subscriber(self, DSPub.Phase.PRE)
        self._agent = None

    def _release_watches(self) -> None:
        for watch in self._watches.values():
            watch.target.tx_ops.remove_subscriber(watch, DSPub.Phase.PRE)
        self._watches = {}

    def _ensure_watch(self, resource: Any) -> None:
        tx_ops = getattr(resource, 'tx_ops', None)
        if tx_ops is None:
            return
        key = id(resource)
        if key not in self._watches:
            watch = _TargetOpsWatch(self, resource)
            tx_ops.add_subscriber(watch, DSPub.Phase.PRE)
            self._watches[key] = watch

    def reset(self) -> None:
        self._release_watches()
        now = float(self._agent.sim.time) if self._agent is not None else 0.0
        self._start_time = now
        self._records: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _target_name(target: Any) -> str:
        return getattr(target, 'name', None) or repr(target)

    def _record(self, rname: str, now: float) -> Dict[str, Any]:
        rec = self._records.get(rname)
        if rec is None:
            rec = {
                'acquired_total': 0.0,
                'released_total': 0.0,
                'balance': 0.0,
                'balance_max': 0.0,
                'balance_integral': 0.0,
                'last_time': now,
                'get_count': 0,
                'put_count': 0,
                'failed_get_count': 0,
                'failed_put_count': 0,
                'preempt_count': 0,
                'preempted_total': 0.0,
            }
            self._records[rname] = rec
        return rec

    @staticmethod
    def _advance(rec: Dict[str, Any], now: float) -> None:
        dt = now - rec['last_time']
        if dt > 0:
            rec['balance_integral'] += rec['balance'] * dt
            rec['last_time'] = now

    def send(self, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return None
        if not isinstance(event, dict) or event.get('kind') != 'agent_state':
            return None
        if event.get('change_type') == 'state':
            return None
        reason = event.get('reason')
        is_get = reason in self.GET_REASONS
        if not is_get and reason not in self.PUT_REASONS:
            return None
        details = event.get('details') or {}
        resource = details.get('resource')
        if resource is None:
            return None
        self._ensure_watch(resource)
        now = float(event.get('time', self._agent.sim.time))
        rec = self._record(self._target_name(resource), now)
        self._advance(rec, now)
        amount = float(details.get('amount') or 0.0)
        success = bool(details.get('success'))
        if is_get:
            if success:
                rec['get_count'] += 1
                rec['acquired_total'] += amount
                rec['balance'] += amount
                if rec['balance'] > rec['balance_max']:
                    rec['balance_max'] = rec['balance']
            else:
                rec['failed_get_count'] += 1
        else:
            if success:
                rec['put_count'] += 1
                rec['released_total'] += amount
                rec['balance'] -= amount
            else:
                rec['failed_put_count'] += 1
        return None

    def _on_target_op(self, resource: Any, event: Any) -> None:
        if not self.enabled or self._agent is None:
            return
        if not isinstance(event, dict) or event.get('kind') != 'resource_op':
            return
        if event.get('op') != 'preempt':
            return
        # The op reports the victim as the owner process registered at acquire time.
        owner = event.get('owner')
        agent = self._agent
        if owner is not getattr(agent, '_scheduled_process', None) and getattr(owner, 'component', None) is not agent:
            return
        now = float(event.get('time', agent.sim.time))
        rec = self._record(self._target_name(resource), now)
        self._advance(rec, now)
        taken = float(event.get('moved') or 0.0)
        rec['preempt_count'] += 1
        rec['preempted_total'] += taken
        rec['balance'] -= taken

    def _resource_stats(self, rec: Dict[str, Any], now: float) -> Dict[str, Any]:
        integral = rec['balance_integral'] + rec['balance'] * max(0.0, now - rec['last_time'])
        duration = now - self._start_time
        result = {k: v for k, v in rec.items() if k != 'last_time'}
        result['balance_integral'] = integral
        result['avg_held'] = integral / duration if duration > 0 else 0.0
        return result

    def amount_held(self, resource: Any) -> float:
        '''Current balance (acquired - released) for `resource` (or its name).'''
        name = resource if isinstance(resource, str) else self._target_name(resource)
        rec = self._records.get(name)
        return rec['balance'] if rec is not None else 0.0

    def amount_acquired(self, resource: Any) -> float:
        '''Total amount successfully acquired from `resource` (or its name).'''
        name = resource if isinstance(resource, str) else self._target_name(resource)
        rec = self._records.get(name)
        return rec['acquired_total'] if rec is not None else 0.0

    def avg_held(self, resource: Any) -> float:
        '''Time-weighted average balance of `resource` over the observation window.'''
        name = resource if isinstance(resource, str) else self._target_name(resource)
        rec = self._records.get(name)
        if rec is None:
            return 0.0
        now = float(self._agent.sim.time) if self._agent is not None else rec['last_time']
        return self._resource_stats(rec, now)['avg_held']

    def stats(self) -> Dict[str, Any]:
        now = float(self._agent.sim.time) if self._agent is not None else self._start_time
        by_resource = {rname: self._resource_stats(rec, now) for rname, rec in self._records.items()}
        return {
            'start_time': self._start_time,
            'end_time': now,
            'duration': now - self._start_time,
            'by_resource': by_resource,
            'acquired_total': sum(r['acquired_total'] for r in by_resource.values()),
            'released_total': sum(r['released_total'] for r in by_resource.values()),
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

    def add_activity_probe(self, enabled: bool = True, name: str = 'activity_probe') -> AgentActivityProbe:
        probe = AgentActivityProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)

    def add_queueing_probe(self, enabled: bool = True, name: str = 'queueing_probe') -> AgentQueueingProbe:
        probe = AgentQueueingProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)

    def add_resource_probe(self, enabled: bool = True, name: str = 'resource_probe') -> AgentResourceProbe:
        probe = AgentResourceProbe(
            enabled=enabled,
            name=f'{self.name}.{name}',
            sim=self.sim,
        )
        return self.add_probe(probe)
