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
CPU Memory Hierarchy Simulation — DSSim PubSubLayer2 variant.

Identical logic to cpu_cache_lite.py (LiteLayer2) but uses PubSubLayer2.
PubSubLayer2 adds condition-stacking, DSFuture, DSFilter, DSCircuit, and
full tier-based routing to the simulator — none of which are used here,
so this implementation serves as a direct overhead comparison.
"""
import random
from collections import OrderedDict

from dssim import DSSimulation, PubSubLayer2

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


class L1Cache:
    def __init__(self, sim):
        self.sim    = sim
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

    def access(self, addr, l2):
        yield from self.sim.gsleep(L1_CYCLES * CYCLE)
        if self.lookup(addr):
            self.hits += 1
        else:
            self.misses += 1
            yield from l2.access(addr, self)


class L2Cache:
    def __init__(self, sim, ram, n_ports=L2_PORTS):
        self.sim    = sim
        self.ram    = ram
        self._sets  = [OrderedDict() for _ in range(L2_SETS)]
        self.hits   = 0
        self.misses = 0
        self._port = sim.unit_resource(amount=n_ports, capacity=n_ports)

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

    def access(self, addr, l1):
        yield from self._port.gget()
        try:
            yield from self.sim.gsleep(L2_CYCLES * CYCLE)
            if self.lookup(addr):
                self.hits += 1
                l1.fill(addr)
            else:
                self.misses += 1
                yield from self.sim.gsleep(MEM_CYCLES * CYCLE)
                self.ram.accesses += 1
                self.fill(addr)
                l1.fill(addr)
        finally:
            self._port.put_nowait()


class RAM:
    def __init__(self):
        self.accesses = 0


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
    sim = DSSimulation(layer2=PubSubLayer2)
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
    print(f"  CPU Cache (PubSubLayer2)  —  {n_accesses:,} accesses")
    print(f"{'─'*52}")
    print(f"  L1  hits {l1.hits:>8,}  misses {l1.misses:>7,}   hit rate {l1_rate:5.1f} %")
    print(f"  L2  hits {l2.hits:>8,}  misses {l2.misses:>7,}   hit rate {l2_rate:5.1f} %")
    print(f"  RAM accesses         {ram.accesses:>7,}")
    print(f"  Average latency  {avg_cy:6.1f} cycles  ({avg_ns:.2f} ns)")
    print(f"{'─'*52}\n")
    return l1, l2, ram, latencies


def run(n_cores=16, n_accesses=200_000, seed=42):
    sim = DSSimulation(layer2=PubSubLayer2)
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
    print(f"  CPU Cache (PubSubLayer2)  —  {n_cores} cores × {n_accesses:,} accesses")
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
    print(f"  Access pattern comparison (PubSubLayer2)  —  N={n:,}  (1 GHz, cycles)")
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
