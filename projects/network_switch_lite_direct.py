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
Case Study: Network Packet Switch (DSSim Lite direct)
======================================================

Direct-call version of the network switch demo.
No pubsub endpoints are used; components call each other directly.

Run:
    python projects/network_switch_lite_direct.py
"""

from dataclasses import dataclass
import random
import statistics

from dssim import DSSimulation, LiteLayer2
from dssim.base_components import DSKeyOrder


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
    """Time-weighted queue length stats (manual, Lite has no pubsub probes)."""

    def __init__(self, sim):
        self._sim = sim
        self._len = 0
        self._area = 0.0
        self._last_t = 0.0
        self._max = 0
        self._get_count = 0

    def _flush(self):
        now = self._sim.time
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
        avg = self._area / self._sim.time if self._sim.time > 0 else 0.0
        return {
            'time_avg_len': avg,
            'max_len': self._max,
            'get_count': self._get_count,
        }


# -- output port -------------------------------------------------------------

class OutputPort:
    """Serializes packets via a FIFO or priority DSLiteQueue."""

    def __init__(self, sim, name='port', capacity=200, policy=None):
        self.sim = sim
        queue_kwargs = dict(capacity=capacity, name=name + '.q')
        if policy is not None:
            queue_kwargs['policy'] = policy
        self.queue = self.sim.queue(**queue_kwargs)

        self.q_stats = QueueStats(sim)
        self._tx_listeners = []
        self.drops = 0
        self._task = self._transmit()
        self.sim.schedule(0, self._task)

    def add_tx_listener(self, fn):
        self._tx_listeners.append(fn)

    def enqueue(self, pkt):
        pkt.born = self.sim.time
        if self.queue.put_nowait(pkt) is None:
            self.drops += 1
            return
        self.q_stats.tally(len(self.queue))

    def _transmit(self):
        while True:
            pkt = yield from self.queue.gget()
            self.q_stats.tally(len(self.queue))
            self.q_stats.on_dequeue()
            pkt.started = self.sim.time
            yield from self.sim.gsleep(pkt.tx_time())
            for fn in self._tx_listeners:
                fn(pkt)


# -- packet source -----------------------------------------------------------

class PacketSource:
    """Generates packets with Poisson inter-arrivals and direct endpoint calls."""

    def __init__(self, sim, endpoint, interval, size, priority, label):
        self.sim = sim
        self.endpoint = endpoint
        self.interval = interval   # mean inter-arrival (us)
        self.size = size
        self.priority = priority
        self.label = label
        self._task = self._run()
        self.sim.schedule(0, self._task)

    def _run(self):
        rng = random.Random(hash(self.label))
        while True:
            yield from self.sim.gsleep(rng.expovariate(1.0 / self.interval))
            pkt = Packet(dst=0, size=self.size, priority=self.priority)
            self.endpoint(pkt)


# -- credited sender ---------------------------------------------------------

class CreditedSender:
    """Direct-call sender with credit and link-state gating (LiteLayer2 only)."""

    def __init__(self, sim, name='sender'):
        self.sim = sim
        self.name = name

        self._credits = MAX_CREDITS
        self._link_up = True

        self._inbox = self.sim.queue(name=self.name + '._inbox')
        # Capacity-1 queue coalesces state-change notifications.
        self._state_signal = self.sim.queue(capacity=1, name=self.name + '._state')

        self._tx_listeners = []
        self.pauses = 0
        self.total_pause_us = 0.0
        self._task = self._sender_loop()
        self.sim.schedule(0, self._task)

    def add_tx_listener(self, fn):
        self._tx_listeners.append(fn)

    def enqueue(self, pkt):
        pkt.born = self.sim.time
        self._inbox.put_nowait(pkt)

    def _notify_state(self):
        # Drop if full: we only need a "state changed" edge.
        self._state_signal.put_nowait(True)

    def set_link(self, state):
        self._link_up = (state == 'UP')
        self._notify_state()

    def add_credits(self, n):
        self._credits = min(self._credits + n, MAX_CREDITS)
        self._notify_state()

    def _sender_loop(self):
        while True:
            pkt = yield from self._inbox.gget()

            t_wait = self.sim.time
            while not (self._link_up and self._credits > 0):
                yield from self._state_signal.gget()
            if self.sim.time > t_wait:
                self.pauses += 1
                self.total_pause_us += self.sim.time - t_wait

            self._credits -= 1

            pkt.started = self.sim.time
            yield from self.sim.gsleep(pkt.tx_time())
            for fn in self._tx_listeners:
                fn(pkt)


# -- helpers -----------------------------------------------------------------

def credit_refiller(sender, sim):
    while True:
        yield from sim.gsleep(REFILL_INTERVAL)
        sender.add_credits(MAX_CREDITS)


def cleanup_task(sim, task):
    sim.cleanup(task)
    try:
        task.close()
    except ValueError:
        pass


def pct(data, p):
    if not data:
        return 0.0
    sd = sorted(data)
    return sd[min(int(len(sd) * p / 100), len(sd) - 1)]


SEP = '-' * 66


# -- isolated component test -------------------------------------------------

def run_isolated(policy=None):
    label = 'FIFO' if policy is None else 'Priority'
    print(f'\n-- Isolated test ({label}) ' + '-' * (40 - len(label)))

    sim = DSSimulation(layer2=LiteLayer2)
    port = OutputPort(sim=sim, name='port', policy=policy)
    log = []

    port.add_tx_listener(lambda p: log.append((sim.time, p.size, p.started - p.born)))

    def feeder():
        port.enqueue(Packet(dst=0, size=1500, priority=7))
        yield from sim.gsleep(1)
        port.enqueue(Packet(dst=0, size=1500, priority=7))
        yield from sim.gsleep(1)
        port.enqueue(Packet(dst=0, size=64, priority=0))

    sim.schedule(0, feeder())
    sim.run(until=50)
    cleanup_task(sim, port._task)

    for t, size, qwait in log:
        print(f't={t:6.2f} us  size={size:4d} B  queue_wait={qwait:6.2f} us')


# -- scenario 1: QoS priority queuing ---------------------------------------

def run_scenario1(policy=None, duration=100_000):
    label = 'FIFO' if policy is None else 'Priority'

    sim = DSSimulation(layer2=LiteLayer2)
    port = OutputPort(sim=sim, name='port', policy=policy)

    voip_lat, bulk_lat = [], []

    def on_exit(pkt):
        qwait = pkt.started - pkt.born
        if pkt.priority == 0:
            voip_lat.append(qwait)
        else:
            bulk_lat.append(qwait)

    port.add_tx_listener(on_exit)

    voip_src = PacketSource(sim, port.enqueue, interval=5, size=64, priority=0, label='voip')
    bulk_src = PacketSource(sim, port.enqueue, interval=15, size=1500, priority=7, label='bulk')

    sim.run(until=duration)
    cleanup_task(sim, voip_src._task)
    cleanup_task(sim, bulk_src._task)
    cleanup_task(sim, port._task)

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
    sim = DSSimulation(layer2=LiteLayer2)
    sender = CreditedSender(sim=sim, name='sender')

    all_lat = []
    sender.add_tx_listener(lambda p: all_lat.append(p.started - p.born))

    voip_src = PacketSource(sim, sender.enqueue, interval=5, size=64, priority=0, label='voip')
    bulk_src = PacketSource(sim, sender.enqueue, interval=15, size=1500, priority=7, label='bulk')

    refill_task = credit_refiller(sender, sim)
    sim.schedule(0, refill_task)

    def fault():
        yield from sim.gsleep(5000)
        sender.set_link('DOWN')
        yield from sim.gsleep(200)
        sender.set_link('UP')

    sim.schedule(0, fault())
    sim.run(until=duration)
    cleanup_task(sim, refill_task)
    cleanup_task(sim, voip_src._task)
    cleanup_task(sim, bulk_src._task)
    cleanup_task(sim, sender._task)

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
    print('=== Isolated component test (Lite direct) ===')
    run_isolated()
    run_isolated(policy=DSKeyOrder(key=lambda p: p.priority))

    print('\n=== Scenario 1: QoS Priority Queuing (Lite direct) ===')
    run_scenario1()
    run_scenario1(policy=DSKeyOrder(key=lambda p: p.priority))

    print('\n=== Scenario 2: Credit-Based Flow Control (Lite direct) ===')
    run_scenario2()
