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
from dssim.simulation import DSComponent, sim
from dssim.pubsub import DSConsumer
from dssim.components.uart import UARTLink, UARTPhys


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # phys = UARTPhys(parity='E')
        phys = None
        self.uart0 = UARTLink(name=self.name + '.uart0', parity='E', tx_buffer_size=10, phys_component=phys)
        self.stat = {'rx_isr_counter': 0}
        self.boot()

    def boot(self):
        # Register ISRs
        self.uart0.rx_irq.add_consumer(DSConsumer(self, MCU.rx_isr, name=self.name + '.isr'))

    def rx_isr(self, flag, **other):
        if flag == 'byte':
            byte = self.uart0.recv()
            if byte is not None:
                self.stat['rx_isr_counter'] += 1
                self.uart0.send(byte)


if __name__ == '__main__':
    cpu0 = MCU(name='cpu0')
    cpu1 = MCU(name='cpu1')

    # connect loopback
    # cpu0.uart0.phys.tx.add_consumer(cpu1.uart0.phys.rx)
    # cpu1.uart0.phys.tx.add_consumer(cpu0.uart0.phys.rx)
    cpu0.uart0.tx.add_consumer(cpu1.uart0.rx)
    cpu1.uart0.tx.add_consumer(cpu0.uart0.rx)

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
