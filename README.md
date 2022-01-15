
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

## Events
The Event object is a Python dictionary (dict) containing information. The reason to choose a dictionary type for an Event class was the flexibility of Python language to use them directly in keyword arguments of the handlers.
* When an Event handler is used, it can specify (by using `DSConsumer`) filter function for the events to be delivered
* When a code `yield sim.wait(...)` for an event, it can specify filter function for the events to be delivered in the `sim.wait(...)` call

## Code executable by the framework
There are several types of functions which could be executed by the framework:
* Event handlers
* Schedulable functions
* Generators
* DSProcess

### Event handler ###
These are handlers (hooks) which are invoked by a specific internal process called `time_queue`. The `time queue` creates an application framework layer for Producers and Consumers (see below).  
Event handler takes the event as the function parameter.

### Schedulable function ###
It is a typical python function, which can be executed in the future. Such function should be decorated with `@DSSchedulable` decorator.  
Schedulable function does not handle any event- it may only produce events.  
The scheduled function is meant to be executed in the future as one-shot, i.e. as a normal function.
The components often define 2 APIs- first for normal call, next for deferred (lazy) call:  
```
def send(data):
    pass

@DSSchedulable  `
def send_lazy(data):  `
    send(data)
```

Meaning that, you cannot create a function X in your simulation and schedule it for later execution without the decorator. At the same time, such decorated function is not callable directly.
```
sim.schedule(5, send_lazy(data))  # This will schedule function in 5 seconds
sim.schedule(5, send(data))       # This won't schedule the send function
send(data)                        # This will immediately call the function
send_lazy(data)                   # This won't call the function
```

Internally, the decorator is converting python function to python generator.

### Generator ###
See [python generator](https://wiki.python.org/moin/Generators) for your reference.  
Here we specifically use such generators, which wait for events from other processes by calling `yield from sim.wait(...)` API.  
Generator is considered to be light-weight `DSProcess`.  
Recommendation is to use DSProcess instead.  

### DSProcess ###
A DSProcess can be created from instantiatized generator by calling `DSProcess(generator(), ...)` constructor.  
The difference between DSProcess and a  generator is that DSPRocess adds another properties which can be used in other APIs.

### Overview ###
Following table can be used for your reference in order to decide what type of code in your simulation:

| ↓ Characteristics / Type of code → | Event handler | Schedulable function | Python generator | DSProcess | Remark / Explanation |
| ------------------------------    | ------------- | -------------------- | ---------------- | --------- | -------------------- |
| Can send immediate signals        | True          | True                 | True             | True      | Signals are events which are emitted immediately |
| Can schedule events               | True          | True                 | True             | True      |                      |
| Can receive events                | True          | False                | True             | True      |                      |
| Schedulable by `sim.schedule()`   | False         | True                 | True             | True      | A event handler can be indirectly scheduled by scheduling an event which it handles |
| Waitable for event by `yield from sim.wait()`| False         | False                | True             | True      | If not waitable, it must not `yield` anywehere in the code body |
| Keeps last value + return value   | False         | False                | False            | True      | The (return) value can be retrieved from `process.value` |
| Can be waited until finish        | False         | False                | False            | True      | A wait for process by `yield from process.join()` |

The simplification rule to decide what type of code to use:
* If you want to create an easy event handler with no intermediate states, use Event Handler 
* Use DSProcess otherwise

## Producers and Consumers
The easier approach used in the simulation is to schedule events and handle them in the event handlers.  
An event is an object containing information about even in the specific time.  
Specifically, a special internal process called `time_process` is created. A `DSProducer` interface defines API to generate event in the future (or now).  
The event is taken by `time_process` and is distributed to all connected `DSConsumer`, which have associated function handler.  

The association between `DSProducer` and `DSConsumer` is typically initialized before the simulation. The simulation application registers the "Producer to Consumer" (Publisher and Subscriber terms are also used) interconnections.  
One Producer can produce events to N Consumers (1:N), where N is from 0 to infinity.  
The interconnection information is stored in the Producer objects (i.e. which Consumers are connected).  

An application creates Producers and Consumers, typically when defining a Component. Every Producer is associated during initialization with Simulator instance.

The DSSIM application defines two types of Consumers:
* A Consumer Handler which runs an event handler function
Such type of consumer handles the event in a function and then returns.
* A Consumer Process
It is a `DSProcess` type of code running typically in an infinite loop. In the loop it `yield sim.wait(...)` for an incoming event. Events are fed by the associated Producer. 

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

In the ISO/OSI stack, the receiver of an information communicates (virtually) with the transmitter of that information in the same level. For instance, a Link Layer of component A communicates with the Link layer of its counterpart.
The virtual communication could be often provided by a Component itself (depends on implementation).

Some Components provide underlying layers. Using the underlying layer (typically specifying it in the Component constructor) a caller can use the typical ISO/OSI stack down to the lowest layer defined.  
With such approach you specify the behavior of peripheral to the lowest detail. The downside is that the performance of the simulation decreases (see Known issues).

# Known issues
The most noticeable downside of DSSIM is its performance (the execution time) . It is caused by the language and the penalty from the language flexibility.
The most important criteria for the execution time is the number of events produced during execution.
The recommended solutions to decrease the simulation time:
1. Define the simulation based on higher abstraction (layer) if possible. In such case the events encapsulate more information and less events are required. As an example, instead of splitting messages to frames and send frame separately, the performance can be updated by sending the whole messages, i.e. to work on higher level of communication from ISO/OSI perspective.
2. Use python executables which have typically higher performance, like PyPy.
