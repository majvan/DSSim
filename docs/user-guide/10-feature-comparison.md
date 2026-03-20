# Chapter 10: Feature Comparison

## 10.1 DSSim vs Other DES Frameworks

The table below compares DSSim's own API with SimPy and salabim on key dimensions.

<table>
<thead>
<tr>
<th>Feature</th>
<th>DSSim (PubSubLayer2)</th>
<th>DSSim (LiteLayer2)</th>
<th>SimPy 4</th>
<th>salabim</th>
</tr>
</thead>
<tbody>
<tr>
<td>Process model</td>
<td style="background-color:#c8e6c9">Generator / coroutine</td>
<td style="background-color:#c8e6c9">Generator / coroutine</td>
<td>Generator</td>
<td>Generator</td>
</tr>
<tr>
<td>Spurious wakeups</td>
<td style="background-color:#c8e6c9">None (condition filtering)</td>
<td style="background-color:#ffcdd2">Possible (no condition gate)</td>
<td style="background-color:#ffcdd2">Possible — when waiting for external state (e.g. credits &amp; link-up), process must poll in a loop; events carry no predicate</td>
<td style="background-color:#ffcdd2">Possible — process wakes on <code>activate()</code> and must re-check condition manually</td>
</tr>
<tr>
<td>Event type</td>
<td style="background-color:#c8e6c9">Any Python object</td>
<td style="background-color:#c8e6c9">Any Python object</td>
<td><code>Event</code> object</td>
<td>Internal</td>
</tr>
<tr>
<td>Publisher-subscriber</td>
<td style="background-color:#c8e6c9">Yes (routing-rich, 4-phase)</td>
<td>Yes (fan-out only)</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Delivery tiers / condition filtering</td>
<td style="background-color:#c8e6c9">Yes (4-phase tiers + conditions)</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Circuit conditions</td>
<td style="background-color:#c8e6c9">Yes (AND/OR)</td>
<td style="background-color:#ffcdd2">No</td>
<td><code>AnyOf</code>/<code>AllOf</code></td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Arbitrary predicate conditions (lambdas)</td>
<td style="background-color:#c8e6c9">Yes — any callable inspecting any simulation state</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No — conditions are event objects, not predicates</td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Resource: variable-amount get / put</td>
<td style="background-color:#c8e6c9">Yes — <code>DSResource</code> <code>gget_n(n)</code> / <code>gput_n(n)</code>, integer or float amounts</td>
<td style="background-color:#c8e6c9">Yes — <code>DSLiteResource</code>, same API</td>
<td style="background-color:#ffcdd2">No — <code>Container</code> supports float amounts but has a different API; <code>Resource</code> is 1-unit only with no general get-n/put-n</td>
<td>Yes — <code>Resource.request(quantity=n)</code></td>
</tr>
<tr>
<td>Resource: unit-only optimized variant</td>
<td style="background-color:#c8e6c9">Yes — <code>DSUnitResource</code>; no per-request <code>_Waiter</code> allocation, optimized dispatch loop</td>
<td style="background-color:#c8e6c9">Yes — <code>DSLiteUnitResource</code>; same + further reduced dispatch overhead</td>
<td style="background-color:#c8e6c9">Yes — <code>Resource</code> is inherently 1-unit and optimized for that case</td>
<td style="background-color:#ffcdd2">No dedicated unit-only variant</td>
</tr>
<tr>
<td>Priority queues</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
</tr>
<tr>
<td>Preemption</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
</tr>
<tr>
<td>No stdlib deps</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes (Tkinter optional)</td>
</tr>
<tr>
<td>asyncio interop</td>
<td style="background-color:#c8e6c9">Yes (shim)</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Point-to-point event delivery</td>
<td style="background-color:#c8e6c9">Yes — <code>sim.send_object()</code> (sync), <code>sim.signal()</code> (now), <code>sim.schedule_event()</code> (future)</td>
<td style="background-color:#c8e6c9">Yes — same three primitives</td>
<td>Partial — <code>event.succeed(value)</code> delivers to a waiting process; tied to event-object model</td>
<td>Partial — <code>component.activate()</code> wakes a process; no payload</td>
</tr>
<tr>
<td>Interruptible processes</td>
<td style="background-color:#c8e6c9">Yes — <code>process.abort()</code></td>
<td style="background-color:#c8e6c9">Yes — <code>process.abort()</code></td>
<td style="background-color:#c8e6c9">Yes — <code>process.interrupt()</code></td>
<td style="background-color:#c8e6c9">Yes — <code>component.activate()</code></td>
</tr>
<tr>
<td>Interruptible context handling</td>
<td style="background-color:#c8e6c9">Yes — <code>sim.interruptible(cond)</code> context manager; condition-gated, structured</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No — <code>process.interrupt()</code> raises an exception directly on the process; not a context, no condition gate</td>
<td style="background-color:#ffcdd2">No</td>
</tr>
<tr>
<td>Probes / statistics</td>
<td style="background-color:#c8e6c9">Yes — built-in and custom probe types</td>
<td style="background-color:#ffcdd2">No</td>
<td style="background-color:#ffcdd2">No</td>
<td>Yes — built-in only, no custom probe types</td>
</tr>
<tr>
<td>Timeout on every wait</td>
<td style="background-color:#c8e6c9">Yes</td>
<td style="background-color:#c8e6c9">Yes</td>
<td>Via <code>Event</code></td>
<td style="background-color:#c8e6c9">Yes</td>
</tr>
</tbody>
</table>

---

## 10.2 Key Takeaways

- DSSim PubSubLayer2 is the most feature-rich profile: condition filtering eliminates spurious wakeups, and the 4-phase pubsub system has no equivalent in SimPy or salabim.
- Both DSSim profiles accept any Python object as an event — no wrapping or base class required. `None` is the universal timeout sentinel across all blocking APIs.
- LiteLayer2 is closer to SimPy in scope, trading routing features for throughput. Both DSSim profiles support interruptible processes (`process.abort()`); structured interruptible context handling (`sim.interruptible(cond)`) is PubSubLayer2-only. SimPy supports process interruption imperatively but has no structured context equivalent.
- All profiles share the same timeout-everywhere convention; SimPy requires explicit `Event` wiring for equivalent behavior.
- For migration paths from SimPy or salabim, see [Chapter 9](09-shims.md).
