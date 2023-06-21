# Copyright 2020- majvan (majvan@gmail.com)
# Copyright 2020 NXP Semiconductors
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
from dssim import DSComponent, DSKWCallback, DSSimulation
from dssim.components.hw.uart import UARTLink, UARTPhys


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # phys = UARTPhys(parity='E')
        phys = None
        self.uart0 = UARTLink(parity='E', tx_buffer_size=10, phys_component=phys, name=self.name + '.uart0', sim=self.sim)
        self.stat = {'rx_isr_counter': 0}
        self.boot()

    def boot(self):
        # Register ISRs
        self.uart0.rx_irq.add_subscriber(DSKWCallback(self.rx_isr, name=self.name + '.isr', sim=self.sim))

    def rx_isr(self, flag, **other):
        if flag == 'byte':
            byte = self.uart0.recv()
            if byte is not None:
                self.stat['rx_isr_counter'] += 1
                self.uart0.send(byte)


if __name__ == '__main__':
    sim = DSSimulation()
    cpu0 = MCU(name='cpu0', sim=sim)
    cpu1 = MCU(name='cpu1', sim=sim)

    # connect loopback
    # cpu0.uart0.phys.tx.add_consumer(cpu1.uart0.phys.rx)
    # cpu1.uart0.phys.tx.add_consumer(cpu0.uart0.phys.rx)
    cpu0.uart0.tx.add_subscriber(cpu1.uart0.rx)
    cpu1.uart0.tx.add_subscriber(cpu0.uart0.rx)

    cpu0.uart0.send(1)
    cpu0.uart0.send(4)
    cpu0.uart0.send(16)
    cpu0.uart0.send(64)
    cpu0.uart0.send(2)

    import cProfile
    cProfile.run('sim.run(10.0)')

    print(cpu0.uart0.stat['tx_counter'])
    print(cpu1.uart0.stat['rx_counter'])
    print(cpu1.uart0.stat['tx_counter'])
    print(cpu0.uart0.stat['rx_counter'])
    print()
    print(cpu1.stat['rx_isr_counter'])
    print(cpu0.stat['rx_isr_counter'])
    print()
    print(sim.num_events)

    assert cpu0.uart0.stat['tx_counter'] == 100173 == cpu1.uart0.stat['rx_counter']
    assert cpu0.uart0.stat['rx_counter'] == 100172 == cpu1.uart0.stat['tx_counter']
    assert sim.num_events == 400690
