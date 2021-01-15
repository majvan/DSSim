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
CPU Memory Hierarchy Simulation — salabim variant.

Mirrors cpu_cache_lite.py but uses salabim instead of DSSim:
  - L1Cache and L2Cache are plain Python objects; their access() methods
    accept a `comp` argument (the salabim.Component that drives the CPU)
    and use `yield comp.hold(delay)` for time advance.
  - CPUCore is a salabim.Component whose process() method walks the workload.
  - env.now() replaces sim.time  (note: salabim uses now() as a method call)

salabim note: yieldless=False is required when using yield inside process().
Each run_*() call creates a fresh salabim.Environment.
"""
import random
from collections import OrderedDict

import salabim

# ── Clock ─────────────────────────────────────────────────────────────────
CLOCK_HZ  = 1_000_000_000
CYCLE     = 1.0 / CLOCK_HZ

# ── Latencies (in cycles) ─────────────────────────────────────────────────
L1_CYCLES  =   4
L2_CYCLES  =  12
MEM_CYCLES = 200

# ── Cache geometry ────────────────────────────────────────────────────────
BLOCK_BYTES = 64
BLOCK_MASK  = ~(BLOCK_BYTES - 1)
L1_LINES    = 64
L2_SETS     = 256
L2_WAYS     = 4
L2_PORTS    = 1

# ── Workload ──────────────────────────────────────────────────────────────
HOT_SIZE    =  2 * 1024
WARM_SIZE   = 32 * 1024
COLD_RANGE  =  1 * 1024 * 1024
HOT_WEIGHT  = 0.50
WARM_WEIGHT = 0.30

# ── Interrupt simulation ───────────────────────────────────────────────────
ISR_BASE     = 0x0F00_0000
ISR_SIZE     =  512
ISR_ACCESSES =   40
IRQ_MEAN_CY  =  5_000


class L1Cache:
    """Direct-mapped cache.  access(addr, l2, comp) yields comp.hold() events."""

    def __init__(self):
        self._tags  = [None] * L1_LINES
        self.hits   = 0
        self.misses = 0

    def _index_and_block(self, addr):
        block = (addr & BLOCK_MASK) >> 6
        index = block % L1_LINES
        return index, block

    def lookup(self, addr):
        index, block = self._index_and_block(addr)
        return self._tags[index] == block

    def fill(self, addr):
        index, block = self._index_and_block(addr)
        self._tags[index] = block

    def access(self, addr, l2, comp):
        yield comp.hold(L1_CYCLES * CYCLE)
        if self.lookup(addr):
            self.hits += 1
        else:
            self.misses += 1
            yield from l2.access(addr, self, comp)


class L2Cache:
    """4-way set-associative LRU cache.  access(addr, l1, comp) yields comp.hold()."""

    def __init__(self, env, ram, n_ports=L2_PORTS):
        self.ram    = ram
        self._sets  = [OrderedDict() for _ in range(L2_SETS)]
        self.hits   = 0
        self.misses = 0
        self._port  = salabim.Resource(capacity=n_ports, env=env)

    def _set_and_block(self, addr):
        block   = (addr & BLOCK_MASK) >> 6
        set_idx = block % L2_SETS
        return set_idx, block

    def lookup(self, addr):
        set_idx, block = self._set_and_block(addr)
        s = self._sets[set_idx]
        if block in s:
            s.move_to_end(block)
            return True
        return False

    def fill(self, addr):
        set_idx, block = self._set_and_block(addr)
        s = self._sets[set_idx]
        if block not in s:
            if len(s) >= L2_WAYS:
                s.popitem(last=False)
            s[block] = True

    def access(self, addr, l1, comp):
        yield comp.request(self._port)
        yield comp.hold(L2_CYCLES * CYCLE)
        if self.lookup(addr):
            self.hits += 1
            l1.fill(addr)
        else:
            self.misses += 1
            yield comp.hold(MEM_CYCLES * CYCLE)
            self.ram.accesses += 1
            self.fill(addr)
            l1.fill(addr)
        comp.release(self._port)


class RAM:
    def __init__(self):
        self.accesses = 0


class CPUCoreIRQ(salabim.Component):
    """CPU core with IRQ support.

    Salabim's interrupt() sets self.interrupted() after the current hold()
    returns — it does not raise through yield-from chains.  Instead, the
    IRQDriver sets an irq_pending flag that is checked between accesses.
    The ISR runs after the completed access; interrupts are masked while
    the ISR itself runs.
    """

    def setup(self, workload, l1, l2, latencies, isr_rng, irq_count):
        self.workload    = workload
        self.l1          = l1
        self.l2          = l2
        self.latencies   = latencies
        self.isr_rng     = isr_rng
        self.irq_count   = irq_count
        self.irq_pending = False
        self.cpu_alive   = True      # IRQDriver polls this to know when to stop

    def process(self):
        for addr in self.workload:
            t0 = self.env.now()
            yield from self.l1.access(addr, self.l2, self)
            self.latencies.append(self.env.now() - t0)
            if self.irq_pending:
                self.irq_pending = False
                self.irq_count[0] += 1
                yield from self._run_isr()
        self.cpu_alive = False

    def _run_isr(self):
        for _ in range(ISR_ACCESSES):
            addr = ISR_BASE + (self.isr_rng.randrange(0, ISR_SIZE) & BLOCK_MASK)
            yield from self.l1.access(addr, self.l2, self)


class IRQDriver(salabim.Component):
    """Fires IRQs at exponential intervals and sets cpu_core.irq_pending."""

    def setup(self, cpu_core, irq_seed):
        self.cpu_core = cpu_core
        self.irq_rng  = random.Random(irq_seed)

    def process(self):
        while self.cpu_core.cpu_alive:
            delay = self.irq_rng.expovariate(1.0 / (IRQ_MEAN_CY * CYCLE))
            yield self.hold(delay)
            self.cpu_core.irq_pending = True


class CPUCore(salabim.Component):
    """Salabim component that drives the cache hierarchy."""

    def setup(self, workload, l1, l2, latencies):
        self.workload  = workload
        self.l1        = l1
        self.l2        = l2
        self.latencies = latencies

    def process(self):
        for addr in self.workload:
            t0 = self.env.now()
            yield from self.l1.access(addr, self.l2, self)
            self.latencies.append(self.env.now() - t0)


# ── Simulation helpers ─────────────────────────────────────────────────────
def run_with_irq(n_cores=1, n_accesses=200_000, seed=42, irq_seed=99):
    """Single- or multi-core run with periodic IRQ using CPUCoreIRQ + IRQDriver."""
    env = salabim.Environment(trace=False, yieldless=False)
    ram = RAM()
    l2  = L2Cache(env, ram)

    all_stats = []
    for core_id in range(n_cores):
        l1        = L1Cache()
        latencies = []
        workload  = make_workload(n_accesses, seed=seed + core_id)
        isr_rng   = random.Random(irq_seed + core_id + 1)
        irq_count = [0]
        all_stats.append((core_id, l1, latencies, irq_count))

        cpu = CPUCoreIRQ(
            name=f'cpu{core_id}', workload=workload, l1=l1, l2=l2,
            latencies=latencies, isr_rng=isr_rng, irq_count=irq_count, env=env,
        )
        IRQDriver(name=f'irq{core_id}', cpu_core=cpu,
                  irq_seed=irq_seed + core_id * 1000, env=env)

    env.run()

    if n_cores == 1:
        _, l1, latencies, irq_count = all_stats[0]
        total_l1 = l1.hits + l1.misses
        total_l2 = l2.hits + l2.misses
        l1_rate  = 100.0 * l1.hits / total_l1 if total_l1 else 0
        l2_rate  = 100.0 * l2.hits / total_l2 if total_l2 else 0
        avg_ns   = sum(latencies) / len(latencies) * 1e9 if latencies else 0
        avg_cy   = avg_ns / (1e9 / CLOCK_HZ)
        print(f"\n{'─'*52}")
        print(f"  CPU Cache (salabim + IRQ)  —  {n_accesses:,} accesses")
        print(f"{'─'*52}")
        print(f"  L1  hits {l1.hits:>8,}  misses {l1.misses:>7,}   hit rate {l1_rate:5.1f} %")
        print(f"  L2  hits {l2.hits:>8,}  misses {l2.misses:>7,}   hit rate {l2_rate:5.1f} %")
        print(f"  RAM accesses         {ram.accesses:>7,}")
        print(f"  Average latency  {avg_cy:6.1f} cycles  ({avg_ns:.2f} ns)")
        print(f"  IRQs serviced  : {irq_count[0]:>7,}"
              f"   ISR accesses : {irq_count[0] * ISR_ACCESSES:>8,}")
        print(f"{'─'*52}\n")
    else:
        print(f"\n{'─'*60}")
        print(f"  CPU Cache (salabim + IRQ)  —  {n_cores} cores × {n_accesses:,} accesses")
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


# ── Workload generators ────────────────────────────────────────────────────
def make_workload(n, seed=42):
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
    rng = random.Random(seed)
    return [rng.randrange(0, HOT_SIZE) & BLOCK_MASK for _ in range(n)]


def make_workload_warm(n, seed=42):
    rng = random.Random(seed)
    return [rng.randrange(0, WARM_SIZE) & BLOCK_MASK for _ in range(n)]


def make_workload_sequential(n, region=32 * 1024):
    return [(i * BLOCK_BYTES) % region for i in range(n)]


def make_workload_strided(n, stride=None):
    if stride is None:
        stride = L1_LINES * BLOCK_BYTES
    n_unique = 8
    return [((i % n_unique) * stride) for i in range(n)]


def make_workload_random(n, seed=42):
    rng = random.Random(seed)
    return [rng.randrange(0, COLD_RANGE) & BLOCK_MASK for _ in range(n)]


# ── Simulation helpers ─────────────────────────────────────────────────────
def _run_one(workload):
    env = salabim.Environment(trace=False, yieldless=False)
    ram = RAM()
    l2  = L2Cache(env, ram)
    l1  = L1Cache()
    latencies = []
    CPUCore(name='cpu', workload=workload, l1=l1, l2=l2, latencies=latencies, env=env)
    env.run()
    return l1, l2, ram, latencies


def run_single(n_accesses=200_000, seed=42):
    workload = make_workload(n_accesses, seed)
    l1, l2, ram, latencies = _run_one(workload)

    total_l1 = l1.hits + l1.misses
    total_l2 = l2.hits + l2.misses
    l1_rate  = 100.0 * l1.hits / total_l1 if total_l1 else 0
    l2_rate  = 100.0 * l2.hits / total_l2 if total_l2 else 0
    avg_ns   = sum(latencies) / len(latencies) * 1e9 if latencies else 0
    avg_cy   = avg_ns / (1e9 / CLOCK_HZ)

    print(f"\n{'─'*52}")
    print(f"  CPU Cache (salabim)  —  {n_accesses:,} accesses")
    print(f"{'─'*52}")
    print(f"  L1  hits {l1.hits:>8,}  misses {l1.misses:>7,}   hit rate {l1_rate:5.1f} %")
    print(f"  L2  hits {l2.hits:>8,}  misses {l2.misses:>7,}   hit rate {l2_rate:5.1f} %")
    print(f"  RAM accesses         {ram.accesses:>7,}")
    print(f"  Average latency  {avg_cy:6.1f} cycles  ({avg_ns:.2f} ns)")
    print(f"{'─'*52}\n")
    return l1, l2, ram, latencies


def run(n_cores=16, n_accesses=200_000, seed=42):
    env = salabim.Environment(trace=False, yieldless=False)
    ram = RAM()
    l2  = L2Cache(env, ram)

    all_stats = []
    for core_id in range(n_cores):
        l1        = L1Cache()
        latencies = []
        all_stats.append((core_id, l1, latencies))
        workload  = make_workload(n_accesses, seed=seed + core_id)
        CPUCore(name=f'cpu{core_id}', workload=workload, l1=l1, l2=l2,
                latencies=latencies, env=env)

    env.run()

    print(f"\n{'─'*60}")
    print(f"  CPU Cache (salabim)  —  {n_cores} cores × {n_accesses:,} accesses")
    print(f"{'─'*60}")
    for core_id, l1, latencies in all_stats:
        total  = l1.hits + l1.misses
        avg_cy = sum(latencies) / len(latencies) / CYCLE
        print(f"  Core {core_id}:  L1 hit {100*l1.hits/total:5.1f} %   avg {avg_cy:.1f} cy")
    l2_total = l2.hits + l2.misses
    print(f"{'─'*60}")
    print(f"  Shared L2:  hit rate {100*l2.hits/l2_total:.1f} %"
          f"   RAM accesses {ram.accesses:,}")
    print(f"{'─'*60}\n")
    return all_stats, l2, ram


def compare_patterns(n=200_000):
    patterns = [
        ("hot_loop   — 2 KB random (fits in L1)",       make_workload_hot(n)),
        ("warm_loop  — 32 KB random (fits in L2)",      make_workload_warm(n)),
        ("sequential — 32 KB scan, repeated",           make_workload_sequential(n)),
        ("strided    — stride=4 KB, 8 distinct blocks", make_workload_strided(n)),
        ("random     — 1 MB uniform",                   make_workload_random(n)),
        ("mixed      — 50% hot / 30% warm / 20% cold",  make_workload(n)),
    ]
    print(f"\n{'─'*72}")
    print(f"  Access pattern comparison (salabim)  —  N={n:,}  (1 GHz, cycles)")
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
    run_with_irq()
