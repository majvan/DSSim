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
Case Study: Network Packet Switch (salabim)
===========================================

Direct-call salabim version of the network switch demo.
No pubsub-style endpoint wiring is used.

Run:
    python projects/network_switch_salabim.py
"""

from collections import deque
from dataclasses import dataclass
import heapq
import random
import statistics

try:
    import salabim
except ImportError as exc:
    raise SystemExit(
        'salabim is required for this demo. Install with: pip install salabim'
    ) from exc


# -- constants ---------------------------------------------------------------

LINK_BYTES_PER_US = 125       # 1 Gbps (125 MB/s = 125 bytes/us)
MAX_CREDITS = 10              # packet slots in receiver buffer
REFILL_INTERVAL = 120         # us between credit grants


# -- packet ------------------------------------------------------------------

@dataclass
class Packet:
    dst: int
    size: int
    priority: int = 4          # 0 = highest, 7 = lowest
    born: float = 0.0          # sim time at enqueue (us)
    started: float = 0.0       # sim time at start-of-service (us)

    def tx_time(self):
        return self.size / LINK_BYTES_PER_US


# -- queue stats -------------------------------------------------------------

class QueueStats:
    """Time-weighted queue length stats accumulated manually."""

    def __init__(self, env):
        self._env = env
        self._len = 0
        self._area = 0.0
        self._last_t = 0.0
        self._max = 0
        self._get_count = 0

    def _flush(self):
        now = self._env.now()
        self._area += self._len * (now - self._last_t)
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
        now = self._env.now()
        avg = self._area / now if now > 0 else 0.0
        return {
            'time_avg_len': avg,
            'max_len': self._max,
            'get_count': self._get_count,
        }


# -- output port -------------------------------------------------------------

class _OutputPortWorker(salabim.Component):
    def setup(self, port):
        self.port = port

    def process(self):
        while True:
            while self.port._len() == 0:
                self.port._has_data.set(False)
                yield self.wait((self.port._has_data, True))

            pkt = self.port._pop()
            self.port.q_stats.tally(self.port._len())
            self.port.q_stats.on_dequeue()

            pkt.started = self.env.now()
            yield self.hold(pkt.tx_time())
            for fn in self.port._tx_listeners:
                fn(pkt)


class OutputPort:
    """Serializes packets via FIFO deque or priority heap."""

    def __init__(self, env, capacity=200, priority_mode=False):
        self.env = env
        self.capacity = capacity
        self.priority_mode = priority_mode

        self._fifo = deque()
        self._prio = []
        self._seq = 0
        self._has_data = salabim.State(name='port.has_data', value=False, env=env)

        self.q_stats = QueueStats(env)
        self._tx_listeners = []
        self.drops = 0

        _OutputPortWorker(name='port.tx', port=self, env=env)

    def _len(self):
        return len(self._prio) if self.priority_mode else len(self._fifo)

    def _pop(self):
        if self.priority_mode:
            _, _, pkt = heapq.heappop(self._prio)
            return pkt
        return self._fifo.popleft()

    def add_tx_listener(self, fn):
        self._tx_listeners.append(fn)

    def enqueue(self, pkt):
        pkt.born = self.env.now()
        if self._len() >= self.capacity:
            self.drops += 1
            return

        if self.priority_mode:
            heapq.heappush(self._prio, (pkt.priority, self._seq, pkt))
            self._seq += 1
        else:
            self._fifo.append(pkt)

        self.q_stats.tally(self._len())
        self._has_data.set(True)


# -- packet source -----------------------------------------------------------

class PacketSource(salabim.Component):
    """Generates packets with Poisson inter-arrivals and direct endpoint calls."""

    def setup(self, endpoint, interval, size, pkt_priority, label):
        self.endpoint = endpoint
        self.interval = interval   # mean inter-arrival (us)
        self.size = size
        self.pkt_priority = pkt_priority
        self.label = label

    def process(self):
        rng = random.Random(hash(self.label))
        while True:
            yield self.hold(rng.expovariate(1.0 / self.interval))
            pkt = Packet(dst=0, size=self.size, priority=self.pkt_priority)
            self.endpoint(pkt)


# -- credited sender ---------------------------------------------------------

class _CreditedSenderWorker(salabim.Component):
    def setup(self, sender):
        self.sender = sender

    def process(self):
        while True:
            while not self.sender._inbox:
                self.sender._has_data.set(False)
                yield self.wait((self.sender._has_data, True))

            pkt = self.sender._inbox.popleft()

            t_wait = self.env.now()
            while not (self.sender._link_up and self.sender._credits > 0):
                cur = self.sender._state_flip.get()
                yield self.wait((self.sender._state_flip, not cur))
            if self.env.now() > t_wait:
                self.sender.pauses += 1
                self.sender.total_pause_us += self.env.now() - t_wait

            self.sender._credits -= 1

            pkt.started = self.env.now()
            yield self.hold(pkt.tx_time())
            for fn in self.sender._tx_listeners:
                fn(pkt)


class CreditedSender:
    """Direct-call salabim sender with credit + link-state gating."""

    def __init__(self, env):
        self.env = env

        self._credits = MAX_CREDITS
        self._link_up = True

        self._inbox = deque()
        self._has_data = salabim.State(name='sender.has_data', value=False, env=env)
        self._state_flip = salabim.State(name='sender.state_flip', value=False, env=env)

        self._tx_listeners = []
        self.pauses = 0
        self.total_pause_us = 0.0

        _CreditedSenderWorker(name='sender.tx', sender=self, env=env)

    def add_tx_listener(self, fn):
        self._tx_listeners.append(fn)

    def enqueue(self, pkt):
        pkt.born = self.env.now()
        self._inbox.append(pkt)
        self._has_data.set(True)

    def _notify_state(self):
        self._state_flip.set(not self._state_flip.get())

    def set_link(self, state):
        self._link_up = (state == 'UP')
        self._notify_state()

    def add_credits(self, n):
        self._credits = min(self._credits + n, MAX_CREDITS)
        self._notify_state()


# -- helper components -------------------------------------------------------

class CreditRefiller(salabim.Component):
    def setup(self, sender):
        self.sender = sender

    def process(self):
        while True:
            yield self.hold(REFILL_INTERVAL)
            self.sender.add_credits(MAX_CREDITS)


class LinkFault(salabim.Component):
    def setup(self, sender):
        self.sender = sender

    def process(self):
        yield self.hold(5000)
        self.sender.set_link('DOWN')
        yield self.hold(200)
        self.sender.set_link('UP')


# -- helpers -----------------------------------------------------------------

def pct(data, p):
    if not data:
        return 0.0
    sd = sorted(data)
    return sd[min(int(len(sd) * p / 100), len(sd) - 1)]


SEP = '-' * 66


def make_env():
    return salabim.Environment(trace=False, yieldless=False)


# -- isolated component test -------------------------------------------------

def run_isolated(priority_mode=False):
    label = 'FIFO' if not priority_mode else 'Priority'
    print(f'\n-- Isolated test ({label}) ' + '-' * (40 - len(label)))

    env = make_env()
    port = OutputPort(env, priority_mode=priority_mode)
    log = []

    port.add_tx_listener(lambda p: log.append((env.now(), p.size, p.started - p.born)))

    class Feeder(salabim.Component):
        def process(self):
            port.enqueue(Packet(dst=0, size=1500, priority=7))
            yield self.hold(1)
            port.enqueue(Packet(dst=0, size=1500, priority=7))
            yield self.hold(1)
            port.enqueue(Packet(dst=0, size=64, priority=0))

    Feeder(name='feeder', env=env)
    env.run(till=50)

    for t, size, qwait in log:
        print(f't={t:6.2f} us  size={size:4d} B  queue_wait={qwait:6.2f} us')


# -- scenario 1: QoS priority queuing ---------------------------------------

def run_scenario1(priority_mode=False, duration=100_000):
    label = 'FIFO' if not priority_mode else 'Priority'

    env = make_env()
    port = OutputPort(env, priority_mode=priority_mode)

    voip_lat, bulk_lat = [], []

    def on_exit(pkt):
        qwait = pkt.started - pkt.born
        if pkt.priority == 0:
            voip_lat.append(qwait)
        else:
            bulk_lat.append(qwait)

    port.add_tx_listener(on_exit)

    PacketSource(
        name='voip_src',
        endpoint=port.enqueue,
        interval=5,
        size=64,
        pkt_priority=0,
        label='voip',
        env=env,
    )
    PacketSource(
        name='bulk_src',
        endpoint=port.enqueue,
        interval=15,
        size=1500,
        pkt_priority=7,
        label='bulk',
        env=env,
    )

    env.run(till=duration)

    s = port.q_stats.stats()

    print(f'\n{SEP}')
    print(f'  {label} output port - {duration:,} us  (1 Gbps link, 90 % offered load)')
    print(SEP)
    if voip_lat:
        print(f'  VoIP (64 B)    packets: {len(voip_lat):6,}   drops: {port.drops}')
        print(f'                 latency avg:{statistics.mean(voip_lat):6.1f} us'
              f'   p50:{pct(voip_lat, 50):6.1f} us'
              f'   p99:{pct(voip_lat, 99):6.1f} us')
    if bulk_lat:
        print(f'  Bulk (1500 B)  packets: {len(bulk_lat):6,}   drops: {port.drops}')
        print(f'                 latency avg:{statistics.mean(bulk_lat):6.1f} us'
              f'   p50:{pct(bulk_lat, 50):6.1f} us'
              f'   p99:{pct(bulk_lat, 99):6.1f} us')
    print(f'  Queue  avg len:{s["time_avg_len"]:6.2f}   max len: {s["max_len"]:3d}')
    print(SEP)


# -- scenario 2: credit-based flow control ----------------------------------

def run_scenario2(duration=10_000):
    env = make_env()
    sender = CreditedSender(env)

    all_lat = []
    sender.add_tx_listener(lambda p: all_lat.append(p.started - p.born))

    PacketSource(
        name='voip_src',
        endpoint=sender.enqueue,
        interval=5,
        size=64,
        pkt_priority=0,
        label='voip',
        env=env,
    )
    PacketSource(
        name='bulk_src',
        endpoint=sender.enqueue,
        interval=15,
        size=1500,
        pkt_priority=7,
        label='bulk',
        env=env,
    )

    CreditRefiller(name='refill', sender=sender, env=env)
    LinkFault(name='fault', sender=sender, env=env)
    env.run(till=duration)

    link_pause_us = 200.0
    credit_pause_us = sender.total_pause_us - link_pause_us
    credit_pauses = sender.pauses - 1

    print(f'\n{SEP}')
    print(f'  Credit-based sender - {duration:,} us (link fault at t=5000-5200 us)')
    print(SEP)
    print(f'  Packets forwarded:  {len(all_lat):5,}   drops: 0')
    print(f'  Credit pauses:      {credit_pauses:5,}   '
          f'total pause: {credit_pause_us:.0f} us'
          f'  ({credit_pause_us / duration * 100:.1f} % of sim time)')
    print('  Link-down pause:        1   duration:    200 us')
    if all_lat:
        print(f'  Avg latency: {statistics.mean(all_lat):5.1f} us'
              f'   p99: {pct(all_lat, 99):5.1f} us')
    print(SEP)


if __name__ == '__main__':
    print('=== Isolated component test (salabim) ===')
    run_isolated(priority_mode=False)
    run_isolated(priority_mode=True)

    print('\n=== Scenario 1: QoS Priority Queuing (salabim) ===')
    run_scenario1(priority_mode=False)
    run_scenario1(priority_mode=True)

    print('\n=== Scenario 2: Credit-Based Flow Control (salabim) ===')
    run_scenario2()
