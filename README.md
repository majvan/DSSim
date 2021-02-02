
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
Simulator is the executable platform of the framework. Its purpose is to schedule processes at specific time. For such, it uses queue of processes scheduled in future time. 
The time queue orders elements by time. In runtime it is fed by application and consumed by the simulator which triggers process afterwards.

Typically, an application creates only one instance of simulator, which has dedicated time queue.

> The DSSIM framework already exports a Simulator object singleton: *dssim.simulation.sim* which is used by all the components if not explicitly specified.

The Simulator also holds the actual time of the simulation.

## Schedulable function calls
Application can define Schedulable function call. Such Schedulable function is scheduled to be run in the future as a process.
We can use two types of the Schedulable:
* A function calling `yield from sim.wait(...)` API: such Schedulable is meant to wait for events or to sleep for defined time
* A normal python function  decorated with `@DSSchedulable` decorator: such function is meant to be executed in the future as one-shot

## Producers and Consumers
Another approach, typically used in the simulation, is to schedule events. An event is an object containing information about even in the specific time. This approach is built on top of the process scheduling.
Specifically, a special process called `time_process` is created and all the Producers encapsulate the event data and schedule the run of the `time_process`. The `time_process`, when scheduled, takes the event, unpacks it and then handles the event object itself.

Before the simulation, the application registers the "Producer to Consumer" (Publisher and Subscriber terms are also used) interconnections.
One Producer can produce events to N Consumers (1:N), where N is from 0 to infinity.
The interconnection information is stored in the Producer objects (i.e. which Consumers are connected).

An application creates Producers and Consumers, typically when defining a Component.
Every Producer is associated during initialization with Simulator instance.

The DSSIM application defines two types of Consumers:
* A Consumer Handler which runs an event handler function
Such type of consumer handles the event in a function and then returns.
* A Consumer Process
Such type of consumer runs typically in an infinite loop and calls some of the sim.wait(...) function to be fed by incoming event. When scheduling an event which is to be signalled into a consumer process, the event is directly put onto process time queue.

## Events
The Event object is a Python dictionary (dict) containing information. The reason to choose a dictionary type for an Event class was the flexibility of Python language to use them directly in keyword arguments of the handlers.
* When a Consumer Handler is constructed, it can specify filter function for the events to be delivered.
* When a Consumer Process waits for an event, it can specify filter function for the events to be waited for.

## Components
A Component is intended to implement a logic which describes the discrete system. Typically, it can describe physical behavior of a hardware component in the Python language. 
The component such consists of three main parts:
* Input Interfaces: Consumers, which wait/consume Events
* Output Interfaces: Producers, which generate Events
* Logic: python code which transfers Events on the input to Events on the output

Both input and output Interfaces are provided either as *private* Producers and Consumers and *public* Producers and Consumers.
> Public endpoints are meant to be used by application to create its own logic on top of them. As an example, an UART component exports TX IRQ and RX IRQ Producer and as well TX Producer and RX Consumer.

The DSSIM framework provides its own pre-programmed Components with logic for basic typical functionality, like UART, etc.

## Application
The simulation Application is typically the top layer Component (i.e. processor and external components on the embedded board).

## Components logic
The application has typical workflow:
1. Pre-simulation
1.1. Application initiates Producers and Consumers
1.2. Application connects every Producer to its Consumers
1.3. Application produces some first Event(s) (kick-on)
2. Application runs Simulator
2.1 Simulator takes Event object from queue and decodes its Producer
2.2 Simulator uses Producer connection to send the Event to all the Consumers connected to the Producer
2.3 The notified Consumer gets Event, runs a logic and typically feeds again the Simulator with new Events for the future
2.4 Simulation ends when there are no events in the queue, or if the max. time required for simulation elapsed

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
1. Schedulable function should be declared with with `@Schedulable` decorator.
2. When any function wants to call a Schedulable function, it should declare itself to be `@Schedulable`.
3. A Schedulable generator is prohibited. That means, the Schedulable must not use its own `yield [value | call(...)]>`.
4. Calling a Schedulable function from Schedulable function is done through `yield from [schedulable_call(...)]>`. It is equivalent of `await` of asyncio Python.
5. If a caller wants to schedule a Schedulable function call from regular event handler, the caller should use `sim.schedule(time_delta, schedulable_call(...))`.

Components export many Schedulable functions.
The DSSIM core exports one Schedulable: `sim.wait(time_delta)`.

This Schedulable is the primitive to build other Schedulables.

# Known issues
The most noticeable downside of DSSIM is its performance (the execution time) . It is caused by the language and the penalty from the language flexibility.
The most important criteria for the execution time is the number of events produced during execution.
The recommended solutions to decrease the simulation time:
1. Define the simulation based on higher abstraction (layer) if possible. In such case the events encapsulate more information and less events are required. As an example, instead of splitting messages to frames and send frame separately, the performance can be updated by sending the whole messages, i.e. to work on higher level of communication from ISO/OSI perspective.
2. Use python executables which have typically higher performance, like PyPy.
