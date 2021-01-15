# PLC-Style Closed-Loop Modeling

This guide shows how to model a PLC-like controller + plant loop in DSSim using `dssim.plc`.

## 1. Define PLC logic as partial rules

Rules are data objects. Each rule has:

- `when`: expression over sensors, actuators, internals
- `writes`: only the tags changed by that rule

```python
from dssim.plc import PLCProgram, rule, var

program = PLCProgram(
    sensors={"s_request", "s_done"},
    actuators={"a_run"},
    internals=set(),
    rules=[
        rule("start_machine", var("s_request") & ~var("s_done"), {"a_run": True}),
        rule("stop_machine", var("s_done"), {"a_run": False}),
    ],
    scan_period=1.0,
)
```

This is a partial-rule model: if a rule does not write a tag, that tag keeps its previous value.

## 2. Define plant actuator->sensor processes

Plant processes declare:

- which actuators they react to
- which sensors they may update
- update function (`transfer`) and optional delay

```python
from dssim.plc import PlantModel, ActuatorSensorProcessSpec

def machine_transfer(event, state):
    if event["value"]:
        return {"s_done": True}
    return {}

plant = PlantModel(processes=[
    ActuatorSensorProcessSpec(
        name="machine",
        actuators={"a_run"},
        sensors={"s_done"},
        transfer=machine_transfer,
        delay=1.0,
    ),
])
```

## 3. Compile logic

Two compile passes are available:

1. `compile_to_actuators(...)` removes rules with no impact on selected actuators.
2. `compile_closed_loop(...)` removes logic/processes not participating in actuator<->sensor feedback.

```python
from dssim.plc import compile_closed_loop

compiled_program, compiled_plant = compile_closed_loop(program, plant)
```

## 4. Simulate with DSSim

Use `build_closed_loop(...)` to instantiate a controller scan process and plant runtime:

```python
from dssim import DSSimulation
from dssim.plc import build_closed_loop

sim = DSSimulation()
controller, plant_runtime = build_closed_loop(
    sim=sim,
    program=program,
    plant=plant,
    initial_state={"s_request": True, "s_done": False, "a_run": False},
)

sim.run(10)
print(controller.state)
```

`controller.tx_actuator` and `controller.tx_scan` can be observed with normal DSSim pubsub subscribers for probing and debugging.
