# DSSim Documentation

DSSim is a discrete-event simulation framework for building process, queue, and resource models.

## Who It Is For

DSSim was created with a wide audience in mind. It is not aimed exclusively at software engineers — it is designed to be approachable for anyone who needs to model a system that changes over time:

- **Scientists and researchers** — model experiments, queuing phenomena, or multi-agent systems without writing a scheduler from scratch.
- **Hardware engineers** — describe bus protocols, pipeline stages, and resource contention in a style close to how hardware behaves: components with input/output endpoints, events flowing between them.
- **Software engineers** — build process-oriented models using generators and coroutines with familiar Python idioms.

The framework adapts to the modeling style that fits the problem, rather than forcing a single paradigm.

## Quick Start

1. [Install](getting-started/install.md) the package and choose a layer profile.
2. Follow the [First Simulation](getting-started/first-sim.md) walkthrough.
3. Read the [Technical User Guide](user-guide/index.md) for the full treatment.
