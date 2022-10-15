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
from dssim.simulation import sim, DSComponent, DSCallback
from dssim.components.i2c import I2CMasterBasic, I2CSlaveBasic


class MCU_master(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.i2c0 = I2CMasterBasic(name=self.name + '.i2c0', sim=self.sim)
        self.stat = {'i2c0_tx_counter': 0, 'i2c0_rx_counter': 0}
        self.boot()

    def boot(self):
        # Register ISRs
        self.i2c0.rx_irq.add_consumer(DSCallback(self.rx_isr, name=self.name + '.isr', sim=self.sim))

    def tx_isr(self, addr, rnw, data=None, **others):
        self.stat['i2c0_tx_counter'] += 1

    def rx_isr(self, addr, rnw, data=None, **others):
        self.stat['i2c0_rx_counter'] += 1
        if rnw:
            # Pretend storing data from slave
            self.i2c0.write(100, [1, 2, 3, 4], startbits=1, stopbits=1, rnw=True)

class MCU_slave(DSComponent):
    def __init__(self, name):
        super().__init__(name)
        self.i2c0 = I2CSlaveBasic(addr=100, name=self.name + '.i2c0', sim=self.sim)
        self.stat = {'i2c0_tx_counter': 0, 'i2c0_rx_counter': 0}

    def boot(self):
        # Register ISRs
        self.i2c0.rx_irq.add_consumer(DSCallback(self.rx_isr, name=self.name + '.isr', sim=self.sim))

    def tx_isr(self, rnw, data=None, **others):
        if data:
            self.stat['i2c0_tx_counter'] += len(data)

    def rx_isr(self, rnw, data=None, **others):
        self.stat['i2c0_rx_counter'] += 1
        if rnw:
            # The following happens in the exact time- it means that the master gets this message
            # as it was reading the message from the bus. Useful to model the single bus master timing
            self.i2c0.reply(data=['A', 'B', 'C', 'D'])

if __name__ == '__main__':
    cpu0 = MCU_master(name='cpu_master0')
    cpu1 = MCU_slave(name='cpu_slave0')

    # connect loopback
    cpu0.i2c0.tx.add_consumer(cpu1.i2c0.rx)
    cpu1.i2c0.tx.add_consumer(cpu0.i2c0.rx)

    cpu0.boot()
    cpu1.boot()

    #cpu0.i2c0.send(0.0, addr=1, data=[1, 2, 3])
    cpu0.i2c0.write(100, [1, 2, 3, 4], startbits=1, stopbits=1, rnw=True)

    sim.run(10.0)

    print(cpu0.i2c0.stat['tx_byte_counter'])
    print(cpu1.i2c0.stat['rx_byte_counter'])
    print(cpu1.i2c0.stat['tx_byte_counter'])
    print(cpu0.i2c0.stat['rx_byte_counter'])
    print()
    print(cpu1.stat['i2c0_rx_counter'])
    print(cpu0.stat['i2c0_rx_counter'])
