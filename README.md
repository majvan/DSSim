
# Digital System Simulator (DSSim)

The Digital System Simulator is a Python framework to simulate deterministic event driven (digital) systems. It simulates time-based behavior of digital components and interaction between them.
# Main goal
The main goal of this simulator is to be able to quickly write a simulation application. The application should be easy to read and understand by anyone who wants to contribute.
The application typically describes everything you do when you want to perform such simulation with hardware.
For instance, if you create an embedded system and communication of a peripheral of an MCU:
1. You design a layer of the components
2. You implement logic of the components of MCU including its peripherals.
3. You connect the components (the external interfaces) on the appropriate level, like you do e.g. with wires and signals on PCB.
5. You run the simulation.

After running such simulation you can connect your own probes / handlers to understand the throughput or data traversal from point A to point B.

# Architecture
## Simulator
Simulator is the executable platform of the framework. It uses queue of events scheduled in future time. The queue contains information about the time (in the future) when the event should be delivered and the event object itself to be delivered.
The simulator processes the time queue (whose elements are ordered by time). The time queue is dynamically fed by application and consumed by the simulator.

Typically, an application creates only one instance of simulator, which has dedicated time queue.

> The DSSIM already exports a Simulation object singleton: *dssim.simulator.sim*.

The Simulator also holds the actual time of the simulation.

## Producers and Consumers
The simulation works on Producer to Consumer (Publisher and Subscriber terms are also used) interconnections.
One Producer can produce events to 1:N Consumers, where N is from 0 to infinity.
The interconnection information is stored in the Producer objects (i.e. which Consumers are connected).

An application creates Producers and Consumers, typically when defining a Component.
Every Producer is associated during initialization with Simulator instance.

The DSSIM application defines two types of Consumers:
* A Consumer Handler which runs an event handler function
Such type of consumer handles the event in a function and then returns.
* A Consumer Process
Such type of consumer runs typically in an infinite loop and calls some of the sim.wait(...) function to be fed by incoming event

Internally, the Simulator creates an instance of one Consumer Process called sim.time_process. This consumer consumes all the events intended for the Consumer Handlers and then
picks the correct handler to call.

## Schedulable function calls
Application can define Schedulable function call. Such Schedulable function is scheduled to be run in the future.
The Schedulable shall be type of Python's generator or it shall be decorated with *@DSSchedulable* decorator.

## Events
The Event object is a Python dictionary (dict) containing information. The reason to choose a dictionary type for an Event class was the flexibility of Python language to use them directly in keyword arguments of the handlers.
When a Consumer Handler is constructed, it can specify filter function for the events to be delivered.
When a Consumer Process waits for an event, it can specify filter function for the events to be waited for.

## Components
The Component creates logic and can be also understood as a definition of hardware behavior in the Python language. 
They create logic between their Consumers and their Producers.
The Components typically provide **private** Producers and Consumers and **public** Producers and Consumers.
> Public endpoints are meant to be used by application to create its own logic on top of them. As an example, an UART component exports TX IRQ and RX IRQ Producer and as well TX Producer and RX Consumer.

The framework provides its own defined Components with logic for basic functionality, like UART, etc.

## Application
The simulation Application is typically set of Components on the top layer (i.e. processor and external components on the embedded board).

## Components logic
The application workflow is as following:
1. Pre-simulation
1.1. Application initiates Producers and Consumers
1.2. Application connects every Producer to its Consumers
1.3. Application produces some first event(s) (kick-on)
2. Application runs Simulator
2.1 Simulator takes Event object from queue and decodes its Producer
2.2 Simulator uses Producer connection to send the Event to all the Consumers connected to the Producer
2.3 The notified Consumer runs some logic and typically feeds again the Simulator with new Events for the future
2.4 Simulation ends when there are no events in the queue, or if the time for simulation elapsed

# Component architecture
The architecture of components could vary from very simple one to the complicated ones. It is recommended to focus on the goal of the project to create simple components
with simple interfaces. For instance, if we are not focused in the behavior of every bit on UART, neither on the message builder, we might create an easy interface which is 
fed by a component and which is delivering full packets an one event.

If the architecture and behavior of the component is very important to the lowest level, it is recommended to split the communication components into layers.
The layers correspond to the ISO/OSI communication stack. Every layer has its own Producers and Consumers.
To understand the principle, let's focus first on the ISO/OSI stack.

In the ISO/OSI stack, the receiver of an information communicates (virtually) with the transmitter of that information in the same level. For instance, a Link Layer of component A
communicates with the Link layer of its counterpart.
The virtual communication could be often provided by a Component itself (depends on implementation).

Some Components provide underlying layers. Using the underlying layer (typically specifying it in the Component constructor) a caller can use the typical ISO/OSI stack down to the lowest layer defined.
With such approach you specify the behavior of peripheral to the lowest detail. The downside is that the performance of the simulation decreases (see Known issues).

# Rules for Schedulable functions
The concept of Schedulable functions is equivalent to the Async functions in Python's asyncio.
1. Schedulable function should be declared with with *@Schedulable* decorator.
2. When any function wants to call a Schedulable function, it should declare itself to be *@Schedulable*.
3. A Schedulable generator is prohibited. That means, the Schedulable must not use *yield [value | call(...)]>*.
4. Calling a Schedulable function from Schedulable function is done through *yield from \[schedulable_call(...)]>*. It is equivalent of *await* of asyncio Python.
5. If a caller wants to schedule a Schedulable function call from regular event handler, the caller should use *sim.schedule(time_delta, schedulable_call(...))*.

Components export many Schedulable functions.
The DSSIM core exports one Schedulable: *sim.wait(time_delta)*.

This Schedulable is the primitive to build other Schedulables.

# Known issues
The most noticeable downside of DSSIM is its performance (the execution time) . It is caused by the language and the penalty from the language flexibility.
The most important criteria for the execution time is the number of events produced during execution.
The recommended solutions to decrease the simulation time:
1. Define the simulation based on higher abstraction (layer) if possible. In such case the events encapsulate more information and less events are required. As an example, instead of splitting messages to frames and send frame separately, the performance can be updated by sending the whole messages, i.e. to work on higher level of communication from ISO/OSI perspective.
2. Use python executables which have typically higher performance, like PyPy.
