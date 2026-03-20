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
Case Study: Network Packet Switch
==================================

Models a single 1 Gbps switch output port forwarding two traffic classes:

  VoIP  — 64 B packets,  Poisson inter-arrival mean 5 μs,  priority 0 (high)
  Bulk  — 1500 B packets, Poisson inter-arrival mean 15 μs, priority 7 (low)

Offered load ≈ 90 %.  Two scenarios are run:

  Scenario 1 — QoS priority queuing
    FIFO queue vs DSKeyOrder priority queue.
    Shows VoIP p99 latency dropping from ~320 μs to ~27 μs.

  Scenario 2 — Credit-based flow control
    sim.wait(lambda) with observe_pre — reads instance variables directly.
    Demonstrates automatic pause/resume on credit exhaustion and link fault.

Run:
    python projects/network_switch.py
"""

from dataclasses import dataclass
import random
import statistics

from dssim import DSSimulation, DSComponent
from dssim.base_components import DSKeyOrder


# ── constants ─────────────────────────────────────────────────────────────────

LINK_BYTES_PER_US = 125       # 1 Gbps  (125 MB/s = 125 bytes/μs)
MAX_CREDITS       = 10        # packet slots in the receiver buffer
REFILL_INTERVAL   = 120       # μs between credit grants from the receiver


# ── Packet ────────────────────────────────────────────────────────────────────

@dataclass
class Packet:
    dst:      int
    size:     int               # bytes
    priority: int  = 4          # 0 = highest, 7 = lowest
    born:     float = 0.0       # sim time when enqueued (μs)
    started:  float = 0.0       # sim time when dequeued / tx started (μs)


def tx_time(pkt):
    """Transmission time in μs for a 1 Gbps link."""
    return pkt.size / LINK_BYTES_PER_US


# ── OutputPort ────────────────────────────────────────────────────────────────

class OutputPort(DSComponent):
    """Serialises packets onto a 1 Gbps link via a FIFO or priority queue."""

    def __init__(self, capacity=200, policy=None, **kwargs):
        super().__init__(**kwargs)

        queue_kwargs = dict(capacity=capacity, name=self.name + '.q')
        if policy is not None:
            queue_kwargs['policy'] = policy
        self.queue = self.sim.queue(**queue_kwargs)

        self.tx    = self.sim.publisher(name=self.name + '.tx')
        self.drops = 0

    def start(self):
        self.sim.process(self._transmit()).schedule(0)

    def enqueue(self, pkt):
        pkt.born = self.sim.time
        if not self.queue.put_nowait(pkt):
            self.drops += 1

    async def _transmit(self):
        while True:
            pkt = await self.queue.get(timeout=float('inf'))
            pkt.started = self.sim.time          # record start-of-service
            await self.sim.sleep(tx_time(pkt))
            self.tx.signal(pkt)


# ── PacketSource ──────────────────────────────────────────────────────────────

class PacketSource:
    """Generates packets with Poisson inter-arrival times."""

    def __init__(self, sim, endpoint, interval, size, priority, label):
        self.sim      = sim
        self.endpoint = endpoint
        self.interval = interval   # mean inter-arrival (μs)
        self.size     = size
        self.priority = priority
        self.label    = label

    def start(self):
        self.sim.schedule(0, self._run())

    def _run(self):
        rng = random.Random(hash(self.label))
        while True:
            yield from self.sim.gwait(rng.expovariate(1.0 / self.interval))
            pkt = Packet(dst=0, size=self.size, priority=self.priority)
            self.sim.signal(pkt, self.endpoint)


# ── CreditedSender ────────────────────────────────────────────────────────────

class CreditedSender(DSComponent):
    """
    Output port with credit-based flow control and link-state gating.

    Both state-change publishers are observed during the wait.  The condition
    lambda reads instance variables directly — no filter/circuit machinery needed.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._credits  = MAX_CREDITS
        self._link_up  = True

        self._inbox      = self.sim.queue(name=self.name + '._inbox')
        self._tx_link    = self.sim.publisher(name=self.name + '._tx_link')
        self._tx_credits = self.sim.publisher(name=self.name + '._tx_credits')

        self.tx             = self.sim.publisher(name=self.name + '.tx')
        self.pauses         = 0
        self.total_pause_us = 0.0

    def start(self):
        proc = self.sim.process(self._sender_loop())
        self._tx_link.add_subscriber(proc, self._tx_link.Phase.PRE)
        self._tx_credits.add_subscriber(proc, self._tx_credits.Phase.PRE)
        proc.schedule(0)

    def enqueue(self, pkt):
        pkt.born = self.sim.time
        self._inbox.put_nowait(pkt)

    def set_link(self, state: str):
        """'UP' or 'DOWN' — immediately blocks or unblocks the sender."""
        self._link_up = (state == 'UP')
        self._tx_link.signal(state)

    def add_credits(self, n: int):
        """Grant n credits from the receiver (capped at MAX_CREDITS)."""
        self._credits = min(self._credits + n, MAX_CREDITS)
        self._tx_credits.signal(self._credits)

    async def _sender_loop(self):
        while True:
            pkt = await self._inbox.get(timeout=float('inf'))

            t_wait = self.sim.time
            await self.sim.check_and_wait(
                cond=lambda e: self._link_up and self._credits > 0
            )
            if self.sim.time > t_wait:
                self.pauses += 1
                self.total_pause_us += self.sim.time - t_wait

            self._credits -= 1
            self._tx_credits.signal(self._credits)   # may drop to 0

            pkt.started = self.sim.time
            await self.sim.sleep(tx_time(pkt))
            self.tx.signal(pkt)


# ── credit refiller ───────────────────────────────────────────────────────────

def credit_refiller(sender, sim):
    """Grants MAX_CREDITS back every REFILL_INTERVAL μs."""
    while True:
        yield from sim.gwait(REFILL_INTERVAL)
        sender.add_credits(MAX_CREDITS)


# ── helpers ───────────────────────────────────────────────────────────────────

def pct(data, p):
    if not data:
        return 0.0
    sd = sorted(data)
    return sd[min(int(len(sd) * p / 100), len(sd) - 1)]


SEP = '─' * 66


# ── isolated component test ───────────────────────────────────────────────────

def run_isolated(policy=None):
    label = 'FIFO' if policy is None else 'Priority'
    print(f'\n── Isolated test ({label}) ' + '─' * (40 - len(label)))

    sim  = DSSimulation()
    port = OutputPort(name='port', sim=sim, policy=policy)
    log  = []

    port.tx.add_subscriber(
        sim.callback(lambda p: log.append((sim.time, p.size, p.started - p.born))),
        port.tx.Phase.PRE,
    )
    port.start()

    def feeder():
        port.enqueue(Packet(dst=0, size=1500, priority=7))
        yield from sim.gwait(1)
        port.enqueue(Packet(dst=0, size=1500, priority=7))
        yield from sim.gwait(1)
        port.enqueue(Packet(dst=0, size=64,   priority=0))

    sim.schedule(0, feeder())
    sim.run(until=50)

    for t, size, qwait in log:
        print(f't={t:6.2f} μs  size={size:4d} B  queue_wait={qwait:6.2f} μs')


# ── scenario 1: QoS priority queuing ─────────────────────────────────────────

def run_scenario1(policy=None, duration=100_000):
    label = 'FIFO' if policy is None else 'Priority'

    sim   = DSSimulation()
    port  = OutputPort(name='port', sim=sim, policy=policy)
    probe = port.queue.add_stats_probe()

    voip_cb = sim.callback(port.enqueue)
    bulk_cb = sim.callback(port.enqueue)

    voip_lat, bulk_lat = [], []

    def on_exit(pkt):
        qwait = pkt.started - pkt.born
        if pkt.priority == 0:
            voip_lat.append(qwait)
        else:
            bulk_lat.append(qwait)

    port.tx.add_subscriber(sim.callback(on_exit), port.tx.Phase.PRE)

    voip_src = PacketSource(sim, voip_cb, interval=5,  size=64,   priority=0, label='voip')
    bulk_src = PacketSource(sim, bulk_cb, interval=15, size=1500, priority=7, label='bulk')

    port.start()
    voip_src.start()
    bulk_src.start()
    sim.run(until=duration)

    s = probe.stats()
    print(f'\n{SEP}')
    print(f'  {label} output port — {duration:,} μs  (1 Gbps link, 90 % offered load)')
    print(SEP)
    if voip_lat:
        print(f'  VoIP (64 B)    packets: {len(voip_lat):6,}   drops: {port.drops}')
        print(f'                 latency avg:{statistics.mean(voip_lat):6.1f} μs'
              f'   p50:{pct(voip_lat, 50):6.1f} μs'
              f'   p99:{pct(voip_lat, 99):6.1f} μs')
    if bulk_lat:
        print(f'  Bulk (1500 B)  packets: {len(bulk_lat):6,}   drops: {port.drops}')
        print(f'                 latency avg:{statistics.mean(bulk_lat):6.1f} μs'
              f'   p50:{pct(bulk_lat, 50):6.1f} μs'
              f'   p99:{pct(bulk_lat, 99):6.1f} μs')
    print(f'  Queue  avg len:{s["time_avg_len"]:6.2f}   max len: {s["max_len"]:3d}')
    print(SEP)


# ── scenario 2: credit-based flow control ────────────────────────────────────

def run_scenario2(duration=10_000):
    sim    = DSSimulation()
    sender = CreditedSender(name='sender', sim=sim)

    voip_cb = sim.callback(sender.enqueue)
    bulk_cb = sim.callback(sender.enqueue)

    all_lat = []

    def on_exit(pkt):
        all_lat.append(pkt.started - pkt.born)

    sender.tx.add_subscriber(sim.callback(on_exit), sender.tx.Phase.PRE)

    voip_src = PacketSource(sim, voip_cb, interval=5,  size=64,   priority=0, label='voip')
    bulk_src = PacketSource(sim, bulk_cb, interval=15, size=1500, priority=7, label='bulk')

    sender.start()
    voip_src.start()
    bulk_src.start()
    sim.schedule(0, credit_refiller(sender, sim))

    def fault():
        yield from sim.gwait(5000)
        sender.set_link('DOWN')
        yield from sim.gwait(200)
        sender.set_link('UP')

    sim.schedule(0, fault())
    sim.run(until=duration)

    # The fault generator contributes exactly one pause of 200 μs.
    # The remaining pauses are credit exhaustion events.
    link_pause_us    = 200.0
    credit_pause_us  = sender.total_pause_us - link_pause_us
    credit_pauses    = sender.pauses - 1

    print(f'\n{SEP}')
    print(f'  Credit-based sender — {duration:,} μs (link fault at t=5000–5200 μs)')
    print(SEP)
    print(f'  Packets forwarded:  {len(all_lat):5,}   drops: 0')
    print(f'  Credit pauses:      {credit_pauses:5,}   '
          f'total pause: {credit_pause_us:.0f} μs'
          f'  ({credit_pause_us / duration * 100:.1f} % of sim time)')
    print(f'  Link-down pause:        1   duration:    200 μs')
    if all_lat:
        print(f'  Avg latency: {statistics.mean(all_lat):5.1f} μs'
              f'   p99: {pct(all_lat, 99):5.1f} μs')
    print(SEP)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=== Isolated component test ===')
    run_isolated()
    run_isolated(policy=DSKeyOrder(key=lambda p: p.priority))

    print('\n=== Scenario 1: QoS Priority Queuing ===')
    run_scenario1()
    run_scenario1(policy=DSKeyOrder(key=lambda p: p.priority))

    print('\n=== Scenario 2: Credit-Based Flow Control ===')
    run_scenario2()
