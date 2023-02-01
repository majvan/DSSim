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
'''
Link layer of the I2C protocol
'''
from dssim.simulation import DSComponent, DSCallback
from dssim.pubsub import DSProducer


class I2CMasterProducer(DSProducer):
    ''' Extension of Producer to handle connected slaves.
    An event sent from this Producer will go only to that slave which
    fits the destination address.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slaves = {}

    def add_consumer(self, consumer):
        ''' Connect a slave to the bus '''
        super().add_consumer(consumer)
        if hasattr(consumer, 'get_addr'):
            addr = consumer.get_addr()
            if addr in self.slaves:
                err_msg = 'Connecting I2C slave {} to master {} impossible' \
                          '- slave address already registered by {}'.format(
                    str(consumer),
                    str(self),
                    str(self.slaves[addr])
                )
                raise ValueError(err_msg)
            self.slaves[addr] = consumer

    def get_slave(self, slave_addr):
        ''' Return the slave with the address or None '''
        return self.slaves.get(slave_addr, None)


class I2CSlaveConsumer(DSCallback):
    ''' Extension of Consumer with associated I2C slave address. '''
    def __init__(self, addr, *args, **kwargs):
        self.addr = addr
        super().__init__(*args, **kwargs)

    def get_addr(self):
        ''' Return the address of the consumer '''
        return self.forward_obj.get_addr()


class I2CMasterBasic(DSComponent):
    ''' This class represents an I2C peripheral in master mode in a controller.
    It is simplified peripheral working on basic link layer.
    '''
    def __init__(self,
                 baudrate=400000,
                 addrsize=7,
                 name='I2CMaster',
                 **kwargs
                 ):
        super().__init__(**kwargs)
        self.bittime = 1 / baudrate
        self.addrsize = addrsize
        # Compute header time without ack delays
        if addrsize == 7:
            self.addrbits = 8 + 1
        elif addrsize == 10:
            self.addrbits = 8 + 1 + 8 + 1
        else:
            raise ValueError('The address size can be only 7 or 10 (in bits).')
        self.last_addr = None

        self.tx_buffer = []
        self.rx_buffer = {}  # mailbox from slaves

        self.stat = {}
        self.stat['tx_byte_counter'] = 0
        self.stat['tx_message_counter'] = 0
        self.stat['rx_byte_counter'] = 0
        self.stat['rx_message_counter'] = 0

        self.tx = I2CMasterProducer(name=self.name + '.tx', sim=self.sim)
        self.tx.add_consumer(DSCallback(
            self._on_sent,
            name=self.name + '.(internal) tx fb',
            sim=self.sim,
        ))
        self.rx = DSCallback(
            self._on_received,
            name=self.name + '.rx',
            sim=self.sim,
        )

        self.tx_irq = DSProducer(name=self.name + '.tx_irq', sim=self.sim)
        self.rx_irq = DSProducer(name=self.name + '.rx_irq', sim=self.sim)

        self.idle = True

    def _send_packet(self, addr, data, startbits, stopbits, rnw=None):
        ''' The basic internal method for computing the timing and scheduling events over I2C.
        The method sends addr (if not None), data array (if not zero length), startbit (if
        requested), stopbits (if requested) and also sends RNW bit information.
        If the bus is busy, it adds the timing into a queue (tx_buffer)
        '''
        if len(self.tx_buffer) > 0:
            return 0  # The TX is locked yet
        if self.idle and not startbits:
            raise ValueError('Cannot start packet without startbit.')
        if stopbits > 1:
            raise ValueError('Stopbits can be max. 1')
        if addr is None:
            if startbits > 0:
                raise ValueError('Address has to be sent always when startbit is sent')
            addrbits = 0
            addr = self.last_addr
        else:
            if startbits > 0:
                self.last_addr = addr
            else:
                if rnw is None:
                    raise ValueError('R/W bit has to be sent when startbit + address is sent')
            addrbits = self.addrbits
        self.tx_buffer.append({
            'addr': addr,
            'rnw': rnw,
            'data': data,
            'startbits': startbits,
            'stopbits': stopbits,
        })
        time_required = (startbits + addrbits + len(data) * 9 + stopbits) * self.bittime
        self.tx.schedule_kw_event(
            time_required,
            addr=addr,
            rnw=rnw,
            data=data,
            startbits=startbits,
            stopbits=stopbits
        )

        self.idle = (stopbits >= 1)
        return 1

    def write(self, addr, data, startbits, stopbits, rnw=None):
        ''' Send typical "write" frame on I2C '''
        return self._send_packet(addr, data, startbits, stopbits, rnw)

    def _on_sent(self, addr, rnw, data=None, **others):
        ''' Feedback after data was sent on I2C- feed with new data '''
        self.stat['tx_message_counter'] += 1
        self.stat['tx_byte_counter'] += 1 + len(data)  # with the addr byte
        if data:
            self.stat['tx_byte_counter'] += len(data)
        self.tx_irq.signal(addr=addr, rnw=rnw, data=data)

    def _on_received(self, addr, rnw, ack, data=None, **others):
        ''' Feedback after data received from I2C slave '''
        if not self.tx_buffer:
            raise ValueError('The bus was not locked by previously started master operation.')
        if self.tx_buffer[0]['addr'] != addr:
            raise ValueError('The bus is locked by other communication with slave')
        sent_data = self.tx_buffer[0]['data']
        self.tx_buffer.pop(0)  # Unlock the bus
        self.stat['rx_message_counter'] += 1
        if data:
            self.stat['rx_byte_counter'] += len(data)
        self.rx_irq.signal(addr=addr, rnw=rnw, ack=ack, sent=sent_data, data=data, **others)

class I2CSlaveBasic(DSComponent):
    ''' Link layer of a slave I2C node '''
    def __init__(self,
                 addr,
                 baudrate=400000,
                 addrsize=7,
                 **kwargs
                 ):
        super().__init__(**kwargs)
        self.bittime = 1 / baudrate
        self.addr = addr
        self.addrsize = addrsize
        self.stat = {}

        self.rx_buffer = None

        self.stat['tx_byte_counter'] = 0
        self.stat['tx_message_counter'] = 0
        self.stat['rx_byte_counter'] = 0
        self.stat['rx_message_counter'] = 0

        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)
        self.rx = I2CSlaveConsumer(
            addr,
            self._on_received,
            cond=lambda e: e['addr'] == self.addr,
            name=self.name + '.rx',
            sim=self.sim
        )
        self.rx_irq = DSProducer(name=self.name + '.rx_irq', sim=self.sim)

    def get_addr(self):
        ''' Return own I2C address '''
        return self.addr

    def reply(self, ack=True, data=None):
        ''' Reply to the master the current sent data, immediatelly '''
        self.stat['tx_message_counter'] += 1
        if data:
            self.stat['tx_byte_counter'] += len(data)
        self.tx.schedule_kw_event(
            0,  # the data has already been sent by master, we just inform the master in return
            addr=self.addr,
            rnw=self.rx_buffer['rnw'],
            ack=ack,
            data=data
        )

    def _on_received(self, rnw, data=None, **others):
        ''' Feedback after data received from I2C master '''
        self.stat['rx_message_counter'] += 1
        self.stat['rx_byte_counter'] += len(data)
        if data:
            self.stat['rx_byte_counter'] += 1 + len(data)  # with the addr byte
        self.rx_buffer = {'rnw': rnw, 'data': data}  # rewrites old
        self.rx_irq.signal(rnw=rnw, data=data, **others)
