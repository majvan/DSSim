# Install

## Requirements

DSSim requires **Python 3.10 or later**. The core simulation runtime has no external dependencies — only the Python standard library.

## Install from Source

```bash
git clone https://github.com/majvan/dssim.git
cd dssim
python3 -m venv .venv
source .venv/bin/activate     # on Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .
```

The `-e` flag installs in editable mode so changes to the source are reflected immediately without reinstalling.

## Verify the Install

```python
from dssim import DSSimulation
sim = DSSimulation()
print("DSSim ready, t =", sim.time)   # DSSim ready, t = 0
```

## Documentation Tooling (optional)

To build or serve the documentation locally:

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve        # live-reload at http://127.0.0.1:8000
mkdocs build        # static output in site/
```

## Run the Examples

```bash
python examples/lite/coro_schedule.py
python "examples/pubsub/Bank, 1 clerk.py"
```

All examples in `examples/` are self-contained and runnable after installing the package.

## Choosing a Layer Profile

DSSim ships two Layer 2 profiles selectable at construction:

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation()                   # PubSubLayer2 — full-featured (default)
sim = DSSimulation(layer2=LiteLayer2)  # LiteLayer2 — lightweight, max throughput
```

| Situation | Choose |
|---|---|
| Small or exploratory project | **PubSubLayer2** |
| Debugging and observability matter (probes, tiers) | **PubSubLayer2** |
| Simulation throughput is the primary constraint | **LiteLayer2** |
| Unsure | **LiteLayer2** — switch to PubSubLayer2 when you hit the first blocker |

Switching from Lite to PubSub later is a one-line change at construction. See [Chapter 2](../user-guide/02-core-concepts.md) for a full comparison.
