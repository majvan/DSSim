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
from dssim import DSComponent, DSSimulation, DSPub, DSTrackableEvent


class Component1(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx = self.sim.publisher(name=self.name + '.tx')

    def emit(self, payload, delay=0):
        self.tx.schedule_event(delay, DSTrackableEvent(payload))


class Component2(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rx = self.sim.callback(self._on_rx, name=self.name + '.rx')
        self.tx = self.sim.publisher(name=self.name + '.tx')
        self.forwarded = 0

    def _on_rx(self, event):
        assert isinstance(event, DSTrackableEvent)
        assert isinstance(event.value, dict)
        assert event.value.get('order_id') == 42
        assert event.value.get('item') == 'widget'
        self.forwarded += 1
        print(f't={self.sim.time}: {self.name} consumed and forwarded {event.value!r}')
        self.tx.signal(event)
        return True  # consume at component #1 endpoint


class Component3(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rx = self.sim.callback(self._on_rx, name=self.name + '.rx')
        self.received = 0

    def _on_rx(self, event):
        assert isinstance(event, DSTrackableEvent)
        assert isinstance(event.value, dict)
        self.received += 1
        endpoint_trace = [pub.name for pub in event.publishers if isinstance(pub, DSPub)]
        full_trace = [getattr(pub, 'name', repr(pub)) for pub in event.publishers]
        assert 'component1.tx' in endpoint_trace
        assert 'component2.tx' in endpoint_trace
        assert 'component2.rx' in full_trace
        print(f't={self.sim.time}: {self.name} got payload: {event.value!r}')
        print(f'endpoint trace: {endpoint_trace}')
        print(f'full trace: {full_trace}')
        return True


if __name__ == '__main__':
    sim = DSSimulation()

    c1 = Component1(name='component1', sim=sim)
    c2 = Component2(name='component2', sim=sim)
    c3 = Component3(name='component3', sim=sim)

    observer_hits = {'a': 0, 'b': 0}
    blocked_consumer_hits = {'n': 0}

    obs_a = sim.callback(lambda e: observer_hits.__setitem__('a', observer_hits['a'] + 1), name='obs_a')
    obs_b = sim.callback(lambda e: observer_hits.__setitem__('b', observer_hits['b'] + 1), name='obs_b')
    blocked_consumer = sim.callback(
        lambda e: blocked_consumer_hits.__setitem__('n', blocked_consumer_hits['n'] + 1) or True,
        name='blocked_consumer',
    )

    # Endpoint #1 has multiple observers and multiple consumers.
    c1.tx.add_subscriber(obs_a, c1.tx.Phase.PRE)
    c1.tx.add_subscriber(obs_b, c1.tx.Phase.PRE)
    c1.tx.add_subscriber(c2.rx, c1.tx.Phase.CONSUME)  # takes the event
    c1.tx.add_subscriber(blocked_consumer, c1.tx.Phase.CONSUME)  # should never run

    # Component #2 forwards through its own endpoint to component #3.
    c2.tx.add_subscriber(c3.rx, c2.tx.Phase.CONSUME)

    c1.emit(payload={'order_id': 42, 'item': 'widget'}, delay=1)
    sim.run(until=5)

    assert observer_hits == {'a': 1, 'b': 1}
    assert c2.forwarded == 1
    assert blocked_consumer_hits['n'] == 0
    assert c3.received == 1
