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
from dssim import DSComponent, DSKWCallback, DSSimulation, DSProducer
from dssim.components.hw.uart import UARTPhys


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.baudrate = 115200
        self.gpio0 = self.sim.producer(name=self.name + '.gpio')
        self.uart0 = UARTPhys(baudrate=self.baudrate, parity='E', name=self.name + '.uart0', sim=self.sim)
        self.gpio0.add_subscriber(self.uart0.rx)  # connect gpio output to UART RX peripheral
        self.stat = {'last_byte': 0}

    def boot(self):
        ''' This function has to be called after producers are registered '''
        # Register ISR routine. The routine is on link layer because physical layer does not
        # export any IRQ (there is not much value to register that a bit was received).
        self.uart0.rx_link.add_subscriber(self.sim.kw_callback(self.rx_isr, name=self.name + '.rx_isr'))

        #  Bit banging with GPIO to send 0x55 = 85
        self.gpio0.schedule_kw_event(0 / self.baudrate, line=0)  # start
        self.gpio0.schedule_kw_event(1 / self.baudrate, line=1)  # bit 0
        self.gpio0.schedule_kw_event(2 / self.baudrate, line=0)
        self.gpio0.schedule_kw_event(3 / self.baudrate, line=1)
        self.gpio0.schedule_kw_event(4 / self.baudrate, line=0)
        self.gpio0.schedule_kw_event(5 / self.baudrate, line=1)
        self.gpio0.schedule_kw_event(6 / self.baudrate, line=0)
        self.gpio0.schedule_kw_event(7 / self.baudrate, line=1)
        self.gpio0.schedule_kw_event(8 / self.baudrate, line=0)  # bit 7
        self.gpio0.schedule_kw_event(9 / self.baudrate, line=1)  # parity
        self.gpio0.schedule_kw_event(10 / self.baudrate, line=1)  # stop

    def rx_isr(self, producer, byte, parity):
        # received a byte. Note that on the physical level the parity is not checked, just reported
        self.stat['last_byte'] = byte

if __name__ == '__main__':
    sim = DSSimulation()
    mcu0 = MCU(name='mcu master', sim=sim)
    mcu0.boot()
    sim.run(0.2)
    print('Received byte', mcu0.stat['last_byte'])
    assert mcu0.stat['last_byte'] == 85
