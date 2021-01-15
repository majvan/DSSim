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
Case Study: CPU Memory Hierarchy Simulation
============================================

Models a CPU core issuing read requests through a 3-level memory hierarchy:

  L1  — 4 KB direct-mapped cache            (4-cycle hit latency)
  L2  — 64 KB 4-way set-associative cache   (12-cycle additional latency)
  RAM — unbounded main memory               (200-cycle additional latency)

Workload mixes hot, warm, and cold accesses so that all three tiers
contribute to the final access-latency distribution:

  50 %  hot   — small 2 KB working set → L1 hits after warm-up
  30 %  warm  — 32 KB working set      → L2 hits, L1 conflicts
  20 %  cold  — random 1 MB space      → RAM misses

Statistics printed at the end:
  hit rates per tier, average access latency, latency breakdown.
"""
import random
from collections import OrderedDict

from dssim import DSSimulation, LiteLayer2

# ── Clock ─────────────────────────────────────────────────────────────────
CLOCK_HZ  = 1_000_000_000          # 1 GHz
CYCLE     = 1.0 / CLOCK_HZ         # seconds per cycle

# ── Latencies (in cycles) ─────────────────────────────────────────────────
L1_CYCLES  =   4                   # cost of an L1 hit
L2_CYCLES  =  12                   # additional cost of an L2 hit (after L1 miss)
MEM_CYCLES = 200                   # additional cost of a RAM fetch (after L2 miss)

# ── Cache geometry ────────────────────────────────────────────────────────
BLOCK_BYTES = 64                   # cache-line size in bytes
BLOCK_MASK  = ~(BLOCK_BYTES - 1)   # mask to align addresses to block boundary

L1_LINES    = 64                   # direct-mapped: 64 × 64 B = 4 KB total
L2_SETS     = 256                  # set-associative: 256 sets
L2_WAYS     = 4                    # 4-way → 256 × 4 × 64 B = 64 KB total
L2_PORTS    = 1                    # number of concurrent request ports

# ── Workload ──────────────────────────────────────────────────────────────
HOT_SIZE    =  2 * 1024            # 2 KB  — fits in L1
WARM_SIZE   = 32 * 1024            # 32 KB — fits in L2, stresses L1
COLD_RANGE  =  1 * 1024 * 1024    # 1 MB  — random, mostly RAM misses
HOT_WEIGHT  = 0.50
WARM_WEIGHT = 0.30
# cold weight = 1 - 0.50 - 0.30 = 0.20

# ── Interrupt simulation ───────────────────────────────────────────────────
ISR_BASE     = 0x0F00_0000    # ISR data — separate address region from main
ISR_SIZE     =  512            # 512 B = 8 blocks — fits entirely in L1
ISR_ACCESSES =   40            # accesses per ISR invocation
IRQ_MEAN_CY  =  5_000          # mean CPU cycles between interrupts (exponential)


class CpuInterrupt(Exception):
    """Raised inside a CPU generator to preempt and trigger ISR execution."""
    pass


# ── L1 Cache: direct-mapped ───────────────────────────────────────────────
class L1Cache:
    """
    Direct-mapped cache.  Each block address maps to exactly one line slot.
    On a conflict the existing line is silently evicted (read-only model).
    """

    def __init__(self, sim):
        self.sim   = sim
        self._tags = [None] * L1_LINES   # None = invalid
        self.hits  = 0
        self.misses = 0

    def _index_and_block(self, addr):
        block = (addr & BLOCK_MASK) >> 6  # block number
        index = block % L1_LINES
        return index, block

    def lookup(self, addr):
        index, block = self._index_and_block(addr)
        return self._tags[index] == block

    def fill(self, addr):
        index, block = self._index_and_block(addr)
        self._tags[index] = block

    # ── DSSim generator ──────────────────────────────────────────────────
    def access(self, addr, l2):
        """Simulate one read.  Yields to the simulator for L1 hit latency,
        then descends to l2.access() on a miss."""
        yield from self.sim.gwait(L1_CYCLES * CYCLE)
        if self.lookup(addr):
            self.hits += 1
        else:
            self.misses += 1
            yield from l2.access(addr, self)   # l2 will call self.fill()


# ── L2 Cache: N-way set-associative ───────────────────────────────────────
class L2Cache:
    """
    4-way set-associative cache with LRU replacement.
    Each set is an OrderedDict{block: True} — most-recently used at the end.
    """

    def __init__(self, sim, ram, n_ports=L2_PORTS):
        self.sim  = sim
        self.ram  = ram
        # One OrderedDict per set: LRU at the front, MRU at the back
        self._sets = [OrderedDict() for _ in range(L2_SETS)]
        self.hits  = 0
        self.misses = 0
        # Port resource: serialises concurrent requests (models L2 arbitration).
        self._port = sim.unit_resource(amount=n_ports, capacity=n_ports)

    def _set_and_block(self, addr):
        block   = (addr & BLOCK_MASK) >> 6
        set_idx = block % L2_SETS
        return set_idx, block

    def lookup(self, addr):
        set_idx, block = self._set_and_block(addr)
        s = self._sets[set_idx]
        if block in s:
            s.move_to_end(block)   # mark as recently used
            return True
        return False

    def fill(self, addr):
        set_idx, block = self._set_and_block(addr)
        s = self._sets[set_idx]
        if block not in s:
            if len(s) >= L2_WAYS:
                s.popitem(last=False)   # evict LRU entry
            s[block] = True

    # ── DSSim generator ──────────────────────────────────────────────────
    def access(self, addr, l1):
        """Called on L1 miss.  Acquires one L2 port, then checks L2 or RAM."""
        yield from self._port.gget()
        try:
            yield from self.sim.gwait(L2_CYCLES * CYCLE)
            if self.lookup(addr):
                self.hits += 1
                l1.fill(addr)
            else:
                self.misses += 1
                yield from self.sim.gwait(MEM_CYCLES * CYCLE)
                self.ram.accesses += 1
                self.fill(addr)
                l1.fill(addr)
        finally:
            self._port.put_nowait()


# ── RAM ───────────────────────────────────────────────────────────────────
class RAM:
    """Unbounded main memory — modelled only as an access counter."""
    def __init__(self):
        self.accesses = 0


# ── Workload generators ───────────────────────────────────────────────────
def make_workload(n, seed=42):
    """50 % hot (2 KB) / 30 % warm (32 KB) / 20 % cold (1 MB) random mix."""
    rng = random.Random(seed)
    addrs = []
    for _ in range(n):
        r = rng.random()
        if r < HOT_WEIGHT:
            addr = rng.randrange(0, HOT_SIZE)
        elif r < HOT_WEIGHT + WARM_WEIGHT:
            addr = rng.randrange(0, WARM_SIZE)
        else:
            addr = rng.randrange(0, COLD_RANGE)
        addrs.append(addr & BLOCK_MASK)
    return addrs


def make_workload_hot(n, seed=42):
    """Random accesses within a 2 KB region — fits entirely in L1."""
    rng = random.Random(seed)
    return [rng.randrange(0, HOT_SIZE) & BLOCK_MASK for _ in range(n)]


def make_workload_warm(n, seed=42):
    """Random accesses within a 32 KB region — fits in L2, stresses L1."""
    rng = random.Random(seed)
    return [rng.randrange(0, WARM_SIZE) & BLOCK_MASK for _ in range(n)]


def make_workload_sequential(n, region=32 * 1024):
    """Sequential block-by-block scan through a region, repeated."""
    return [(i * BLOCK_BYTES) % region for i in range(n)]


def make_workload_strided(n, stride=None):
    """Stride = L1 size (4 KB): all accesses map to the same L1 slot."""
    if stride is None:
        stride = L1_LINES * BLOCK_BYTES   # 4096 bytes
    n_unique = 8
    return [((i % n_unique) * stride) for i in range(n)]


def make_workload_random(n, seed=42):
    """Uniform random across the full 1 MB address space."""
    rng = random.Random(seed)
    return [rng.randrange(0, COLD_RANGE) & BLOCK_MASK for _ in range(n)]


# ── Statistics printer ────────────────────────────────────────────────────
def print_stats(l1, l2, ram, latencies, n_accesses):
    total_l1 = l1.hits + l1.misses
    total_l2 = l2.hits + l2.misses

    l1_hit_rate = 100.0 * l1.hits  / total_l1  if total_l1 else 0.0
    l2_hit_rate = 100.0 * l2.hits  / total_l2  if total_l2 else 0.0
    ram_rate    = 100.0 * ram.accesses / total_l1 if total_l1 else 0.0

    avg_ns      = (sum(latencies) / len(latencies)) * 1e9 if latencies else 0.0
    avg_cycles  = avg_ns / (1e9 / CLOCK_HZ)

    # Expected average cycles (analytical):
    # avg = L1_CYCLES + miss_rate_l1*(L2_CYCLES + miss_rate_l2*(MEM_CYCLES))
    mr1 = l1.misses / total_l1 if total_l1 else 0
    mr2 = l2.misses / total_l2 if total_l2 else 0
    expected = L1_CYCLES + mr1 * (L2_CYCLES + mr2 * MEM_CYCLES)

    print(f"\n{'─'*52}")
    print(f"  CPU Cache Simulation  —  {n_accesses:,} accesses")
    print(f"{'─'*52}")
    print(f"  L1  hits  {l1.hits:>8,}  misses {l1.misses:>7,}   hit rate {l1_hit_rate:5.1f} %")
    print(f"  L2  hits  {l2.hits:>8,}  misses {l2.misses:>7,}   hit rate {l2_hit_rate:5.1f} % (of L1 misses)")
    print(f"  RAM accesses          {ram.accesses:>7,}            ({ram_rate:.1f} % of total)")
    print(f"{'─'*52}")
    print(f"  Average latency   {avg_cycles:6.1f} cycles  ({avg_ns:.2f} ns)")
    print(f"  Expected latency  {expected:6.1f} cycles  (analytical)")
    print(f"{'─'*52}\n")


# ── Simulation entry point ────────────────────────────────────────────────
def run_with_irq(n_cores=1, n_accesses=200_000, seed=42, irq_seed=99):
    """Single- or multi-core run with periodic IRQ.

    Each core has a private L1 and a paired irq_driver generator that fires
    at exponential intervals (mean = IRQ_MEAN_CY cycles).  The driver sets
    an irq_pending flag polled between accesses; the core then runs the ISR.
    Polling avoids signals arriving while a core is blocked on the shared
    L2 resource port, which would corrupt the resource waiter queue.
    """
    sim = DSSimulation(layer2=LiteLayer2)
    ram = RAM()
    l2  = L2Cache(sim, ram)

    all_stats = []
    for core_id in range(n_cores):
        l1          = L1Cache(sim)
        latencies   = []
        workload    = make_workload(n_accesses, seed=seed + core_id)
        isr_rng     = random.Random(irq_seed + core_id + 1)
        irq_pending = [False]
        cpu_done    = [False]
        irq_count   = [0]
        all_stats.append((core_id, l1, latencies, irq_count))

        def _isr(l1=l1, isr_rng=isr_rng):
            for _ in range(ISR_ACCESSES):
                addr = ISR_BASE + (isr_rng.randrange(0, ISR_SIZE) & BLOCK_MASK)
                yield from l1.access(addr, l2)

        def cpu(l1=l1, latencies=latencies, workload=workload,
                irq_pending=irq_pending, cpu_done=cpu_done,
                irq_count=irq_count, _isr=_isr):
            for addr in workload:
                t0 = sim.time
                yield from l1.access(addr, l2)
                latencies.append(sim.time - t0)
                if irq_pending[0]:
                    irq_pending[0] = False
                    irq_count[0] += 1
                    yield from _isr()
            cpu_done[0] = True

        def irq_driver(irq_pending=irq_pending, cpu_done=cpu_done,
                       irq_rng=random.Random(irq_seed + core_id * 1000)):
            while not cpu_done[0]:
                delay = irq_rng.expovariate(1.0 / (IRQ_MEAN_CY * CYCLE))
                yield from sim.gwait(delay)
                irq_pending[0] = True

        sim.schedule(0, cpu())
        sim.schedule(0, irq_driver())

    sim.run()

    if n_cores == 1:
        _, l1, latencies, irq_count = all_stats[0]
        print_stats(l1, l2, ram, latencies, n_accesses)
        print(f"  IRQs serviced : {irq_count[0]:>7,}"
              f"   ISR accesses : {irq_count[0] * ISR_ACCESSES:>8,}\n")
    else:
        print(f"\n{'─'*60}")
        print(f"  CPU Cache + IRQ  —  {n_cores} cores × {n_accesses:,} accesses")
        print(f"{'─'*60}")
        for core_id, l1, latencies, irq_count in all_stats:
            total  = l1.hits + l1.misses
            avg_cy = sum(latencies) / len(latencies) / CYCLE
            print(f"  Core {core_id}:  L1 hit {100*l1.hits/total:5.1f} %"
                  f"   avg {avg_cy:.1f} cy   IRQs {irq_count[0]:,}")
        l2_total = l2.hits + l2.misses
        print(f"{'─'*60}")
        print(f"  Shared L2:  hit rate {100*l2.hits/l2_total:.1f} %"
              f"   RAM accesses {ram.accesses:,}")
        print(f"{'─'*60}\n")
    return all_stats, l2, ram


def run_single(n_accesses=200_000, seed=42):
    """Single-core run.  Used for access-pattern comparison and correctness checks."""
    sim = DSSimulation(layer2=LiteLayer2)
    ram = RAM()
    l2  = L2Cache(sim, ram)
    l1  = L1Cache(sim)

    workload  = make_workload(n_accesses, seed)
    latencies = []

    def cpu():
        for addr in workload:
            t0 = sim.time
            yield from l1.access(addr, l2)
            latencies.append(sim.time - t0)

    sim.schedule(0, cpu())
    sim.run()

    print_stats(l1, l2, ram, latencies, n_accesses)
    return l1, l2, ram, latencies


def run(n_cores=16, n_accesses=200_000, seed=42):
    """Multi-core run: each core has a private L1, all share one L2 and RAM."""
    sim = DSSimulation(layer2=LiteLayer2)
    ram = RAM()
    l2  = L2Cache(sim, ram)

    all_stats = []
    for core_id in range(n_cores):
        l1        = L1Cache(sim)
        latencies = []
        all_stats.append((core_id, l1, latencies))
        workload  = make_workload(n_accesses, seed=seed + core_id)

        def cpu(l1=l1, latencies=latencies, workload=workload):
            for addr in workload:
                t0 = sim.time
                yield from l1.access(addr, l2)
                latencies.append(sim.time - t0)

        sim.schedule(0, cpu())

    sim.run()

    print(f"\n{'─'*60}")
    print(f"  CPU Cache Simulation  —  {n_cores} cores × {n_accesses:,} accesses")
    print(f"{'─'*60}")
    for core_id, l1, latencies in all_stats:
        total = l1.hits + l1.misses
        avg_cy = sum(latencies) / len(latencies) / CYCLE
        print(f"  Core {core_id}:  L1 hit {100*l1.hits/total:5.1f} %"
              f"   avg {avg_cy:.1f} cy")
    l2_total = l2.hits + l2.misses
    print(f"{'─'*60}")
    print(f"  Shared L2:  hit rate {100*l2.hits/l2_total:.1f} %"
          f"   RAM accesses {ram.accesses:,}")
    print(f"{'─'*60}\n")
    return all_stats, l2, ram


def _run_one(workload):
    """Run a single workload; return (l1, l2, ram, latencies)."""
    sim = DSSimulation(layer2=LiteLayer2)
    ram = RAM()
    l2  = L2Cache(sim, ram)
    l1  = L1Cache(sim)
    latencies = []

    def cpu():
        for addr in workload:
            t0 = sim.time
            yield from l1.access(addr, l2)
            latencies.append(sim.time - t0)

    sim.schedule(0, cpu())
    sim.run()
    return l1, l2, ram, latencies


def compare_patterns(n=200_000):
    """Run six access patterns and print a comparison table."""
    patterns = [
        ("hot_loop   — 2 KB random (fits in L1)",         make_workload_hot(n)),
        ("warm_loop  — 32 KB random (fits in L2)",        make_workload_warm(n)),
        ("sequential — 32 KB scan, repeated",             make_workload_sequential(n)),
        ("strided    — stride=4 KB, 8 distinct blocks",   make_workload_strided(n)),
        ("random     — 1 MB uniform",                     make_workload_random(n)),
        ("mixed      — 50% hot / 30% warm / 20% cold",    make_workload(n)),
    ]

    print(f"\n{'─'*72}")
    print(f"  Access pattern comparison  —  N={n:,}  (1 GHz, cycles)")
    print(f"{'─'*72}")
    print(f"  {'Pattern':<46} {'L1 hit':>6}  {'L2 hit':>6}  {'RAM':>7}  {'avg cy':>7}")
    print(f"{'─'*72}")
    for label, wl in patterns:
        l1, l2, ram, lat = _run_one(wl)
        tl1 = l1.hits + l1.misses
        tl2 = l2.hits + l2.misses
        l1r = 100.0 * l1.hits / tl1
        l2r = 100.0 * l2.hits / tl2 if tl2 else 0.0
        avg = sum(lat) / len(lat) / CYCLE
        print(f"  {label:<46} {l1r:5.1f}%  {l2r:5.1f}%  {ram.accesses:>7,}  {avg:>7.1f}")
    print(f"{'─'*72}\n")


if __name__ == '__main__':
    run()
    compare_patterns()
    run_single()
    run_with_irq()
