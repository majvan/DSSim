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
UART components- physical layer nad link layer.
Link layer components can (but not necessarily has to) use physical layer
'''
import random as _rand
from dssim.simulation import DSSchedulable, DSComponent, DSCallback, DSProcess
from dssim.pubsub import DSProducer
from dssim.utils import ParityComputer, ByteAssembler


def get_bits_per_byte(bits, stopbit, startbit, parity):
    ''' Return number of bits per frame depending on the link layer setting '''
    retval = bits + stopbit + startbit
    if parity in ('E', 'O'):
        retval += 1
    return retval


class UARTNoisyLine(DSComponent):
    ''' This class represents one direction serial line with a noise.

    The noise is represented by the probability of incorrect bit.
    '''
    # A resolution is 1 / resolution
    resolution = 1e12

    def __init__(self, bit_error_probability=1e-9, **kwargs):
        super().__init__(**kwargs)
        self.probability_level = int(bit_error_probability * self.resolution)
        # The random module is required when using this component
        self._rand = _rand
        self.rx = DSCallback(
            self._on_rx_event,
            name=self.name + '.rx',
            sim=self.sim,
        )
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)

        self.stat = {}
        self.stat['bit_counter'] = 0  # counter of bits received
        self.stat['bit_err_counter'] = 0  # counter of bits getting flipped
        self.stat['byte_counter'] = 0  # counter of bytes received
        self.stat['byte_err_counter'] = 0  # counter of bytes which were modified
        self.stat['byte_link_counter'] = 0  # counter of bytes which were dropped

    def _on_rx_event(self, **data):
        ''' Compute for every bit some random value (noise amplitude) with normal probability
        if the probability is above a threshold, inject error.
        '''
        bits_per_byte = get_bits_per_byte(
            data['bits'],
            data['stopbit'],
            data['startbit'],
            data['parity']
        )
        self.stat['byte_counter'] += 1
        self.stat['bit_counter'] += bits_per_byte
        errors = []
        for _ in range(int(bits_per_byte)):
            errors.append(self.probability_level > self._rand.randint(0, self.resolution))
        if errors[0] or errors[-1]:
            self.stat['byte_link_counter'] += 1
            # an error in start bit or stop bit means that the byte is not properly
            # sent in link layer and it is skipped
            return
        errors = errors[1:-1]
        # Compute resulting parity
        if 'parity_bit' in data and errors[-1]:
            self.stat['bit_err_counter'] += 1
            data['parity_bit'] = data['parity_bit'] ^ 1
            errors = errors[:-1]
        if any(errors):
            flip_bits = 0
            self.stat['byte_err_counter'] += 1
            for err in errors:
                flip_bits = flip_bits << 1
                if err:
                    self.stat['bit_err_counter'] += 1
                    flip_bits += 1
            # Compute resulting output bytes
            if isinstance(data['byte'], str):
                data['byte'] = chr(ord(data['byte']) ^ flip_bits)
            else:
                data['byte'] ^= flip_bits
        self.tx.signal(**data)


class UARTPhysBase(DSComponent):
    ''' Physical layer of an UART component '''
    def __init__(self,
                 baudrate=115200,
                 bits=8,
                 stopbit=1.5,
                 startbit=1,
                 parity='N',
                 tx_buffer_size=1,
                 rx_buffer_size=1,
                 **kwargs
                 ):
        super().__init__(**kwargs)
        self.baudrate = baudrate
        self.bits = bits
        self.stopbit = stopbit
        self.startbit = startbit
        self.parity = parity
        self.bittime = 1 / baudrate
        self.bits_per_byte = get_bits_per_byte(bits, stopbit, startbit, parity)
        self.bytetime = self.bits_per_byte * self.bittime

        self._add_tx_pubsub()
        self._add_rx_pubsub()

        self.tx_buffer = []
        self.tx_buffer_size = tx_buffer_size + 1  # we keep transmitting byte in the buffer
        self.rx_buffer = []
        self.rx_buffer_size = rx_buffer_size

    def _add_tx_pubsub(self):
        self.tx = DSProducer(name=self.name + '.tx')
        # self.tx_irq = DSProducer(name=self.name + '.tx_irq')  # Not supported yet, low value
        self.tx_link = DSProducer(name=self.name + '.tx bridge to linklayer', sim=self.sim)

    def _add_rx_pubsub(self):
        # self.rx_irq = DSProducer(name=self.name + '.rx_irq')  # Not supported now, low value
        self.rx_link = DSProducer(name=self.name + '.rx bridge to linklayer', sim=self.sim)

    def send(self, byte, parity):
        ''' Send a byte over UART with and a parity bit '''
        if len(self.tx_buffer) == 0:
            self.tx_buffer.append({'byte': byte, 'parity': parity})
            self._send_now(byte, parity)
            return 1
        if len(self.tx_buffer) < self.tx_buffer_size:
            self.tx_buffer.append({'byte': byte, 'parity': parity})
            return 1
        return None

    def recv(self):
        ''' Receive byte from UART peripheral '''
        if len(self.rx_buffer) > 0:
            return self.rx_buffer.pop(0)
        return None

    def _send_now(self, byte, parity, *other):
        pass

    def _send_next(self):
        ''' Send next buffered byte over UART '''
        free_slot = False
        # Free slot in the physical layer
        if len(self.tx_buffer) > 0:
            self.tx_buffer.pop(0)  # this one was already transferred
            free_slot = True
        # Check if we have anything to send; first in the physical buffer
        if len(self.tx_buffer) > 0:
            data = self.tx_buffer[0]
            self._send_now(**data)
        # And if possible, inform link layer to push data again
        if free_slot:
            # Inform top layer about free slot in tx_buffer
            self.tx_link.signal(producer=self.tx_link, flag='byte')


class UARTPhys(UARTPhysBase):
    ''' This class represents an UART peripheral in a controller working
    on simplified physical layer.

    The machine follows the state of bits to be sent, together with
    '''

    def __init__(self,
                 baudrate=115200,
                 bits=8,
                 stopbit=1.5,
                 startbit=1,
                 parity='N',
                 **kwargs
                 ):
        super().__init__(baudrate, bits, stopbit, startbit, parity, 1, 1, **kwargs)
        self.tx_line_state = 0
        self.rx_line_state = 1

        self.stat = {}
        self.stat['noise_counter'] = 0
        self.stat['tx_counter'] = 0  # TX bytes counter
        self.stat['rx_counter'] = 0  # RX bytes counter
        self.stat['err_underrun'] = 0  # TX underrun counter (app too fast to send)
        self.stat['err_overrun'] = 0  # RX overruns counter (app to slow to recv)

        self.__add_tx_pubsub()
        self.__add_rx_pubsub()

        self._tx_idle_now()

    def send(self, *args, **kwargs):
        retval = super().send(*args, **kwargs)
        if retval is None:
            self.stat['err_underrun'] += 1
        return retval

    def __add_tx_pubsub(self):
        pass

    def __add_rx_pubsub(self):
        # Create new interface for RX
        self.rx = DSCallback(
            self._on_rx_line_state,
            name=self.name + '.rx',
            sim=self.sim,
        )
        self._rx_sampler = DSProcess(
            self._scan_bits(),
            name=self.name + '.rx_sampler',
            sim=self.sim,
        )
        self._rx_sampler.schedule(0)

    def _send_now(self, byte, parity, *other):
        ''' Working byte, we will shift this byte right to get the bits.

        The initial shift by one bit left here is to prepare for the state machine.
        The state machine first shifts and then gets the bit.
        It is done this way to have the LSb information available during sending byte
        without requiring to save it to other variable.
        '''
        # TODO: add if the byte should be sent with LSb or MSb first. Currently it is LSb first.
        bits = []
        for _ in range(self.bits):
            bits.append(byte & 0x01)
            byte >>= 1
        self.sim.schedule(0, self._send_bits(bits, parity))

    def _tx_idle_now(self):
        self._set_tx_line_state(1)

    def _set_tx_line_state(self, state):
        if self.tx_line_state != state:
            self.tx_line_state = state
            self.tx.signal(line=state)

    def _on_rx_line_state(self, line, **others):
        self.rx_line_state = line
        # the sampler also requires in some cases async information about line change
        # notify only the _rx_sampler; possible only when this method is run
        # within other process than _rx_sampler
        self._rx_sampler.signal(line=line)

    def _send_bits(self, bits, parity_bit=None):
        # schedule set of next events
        time = 0
        line = 0
        self.tx.schedule(time, line=0)
        time += self.startbit * self.bittime
        for bit in bits:
            if bit != line:
                line = bit
                self.tx.schedule(time, line=line)
            time += self.bittime
        if parity_bit is not None:
            if parity_bit != line:
                line = parity_bit
                self.tx.schedule(time, line=line)
            time += self.bittime
        if line != 1:
            self.tx.schedule(time, line=1)
        yield from self.sim.wait(self.bytetime)
        self.stat['tx_counter'] += 1  # TX bytes counter
        self._send_next()

    def _scan_bits(self):
        # Assuming flag == 'line', then flag_details == line state
        while True:
            # wait for start bit
            yield from self.sim.wait(cond=lambda e: e['line'] == 0)
            # wait till end of start bit
            evt = yield from self.sim.wait(
                (self.startbit - 0.5) * self.bittime,
                lambda e: e['line'] == 1
            )
            if evt is not None:
                # we received logical 1 during startbit, go to the start
                self.stat['noise_counter'] += 1
                continue
            rx_bits = []
            for _ in range(self.bits):
                yield from self.sim.wait(self.bittime)
                rx_bits.append(self.rx_line_state)
            if self.parity in ('E', 'O'):
                yield from self.sim.wait(self.bittime)
                rx_parity_bit = self.rx_line_state
            else:
                rx_parity_bit = None
            # wait for stop bit
            yield from self.sim.wait(self.bittime)
            if self.rx_line_state != 1:
                self.stat['noise_counter'] += 1
                continue
            # wait till end of stop bit
            evt = yield from self.sim.wait(
                (self.stopbit - 0.5 - 0.1) * self.bittime,
                lambda e: e['line'] == 0,
            )
            if evt is not None:
                # we received logical 0 during startbit, go to the start
                continue
            self.stat['rx_counter'] += 1  # RX bytes counter
            rx_byte = ByteAssembler(rx_bits).get(lsb=True)
            self.rx_link.signal(producer=self.rx,  # fake the producer
                                byte=rx_byte,
                                parity=rx_parity_bit,
                                )


class UARTPhysBasic(UARTPhysBase):
    ''' This class represents an UART peripheral in a controller working
    on simplified physical layer.

    The machine follows the state of bits to be sent, together with
    '''

    def __init__(self,
                 baudrate=115200,
                 bits=8,
                 stopbit=1.5,
                 startbit=1,
                 parity='N',
                 **kwargs
                 ):
        super().__init__(baudrate, bits, stopbit, startbit, parity, 1, 1, **kwargs)
        self.tx_buffer = []
        self.tx_buffer_size = 1  # on this level it should not be more

        self.__add_tx_pubsub()
        self.__add_rx_pubsub()

        self.stat = {}
        self.stat['noise_counter'] = 0
        self.stat['tx_counter'] = 0  # TX bytes counter
        self.stat['rx_counter'] = 0  # RX bytes counter
        self.stat['err_underrun'] = 0  # TX underrun counter (app too fast to send)
        self.stat['err_overrun'] = 0  # RX overruns counter (app to slow to recv)

    def __add_tx_pubsub(self):
        consumer = DSCallback(self._on_tx_byte_event,
                              name=self.name + '.(internal) tx fb',
                              sim=self.sim
                              )
        self.tx.add_subscriber(consumer)

    def __add_rx_pubsub(self):
        # Create new interface for RX
        self.rx = DSCallback(self._on_rx_byte_event,
                             name=self.name + '.rx',
                             sim=self.sim
                             )

    def _send_now(self, byte, parity, *other):
        self.tx.schedule(self.bytetime, byte=byte, parity=parity)

    def _on_tx_byte_event(self, producer, byte, parity, **event_data):
        self.stat['tx_counter'] += 1
        self._send_next()

    def _on_rx_byte_event(self, producer, byte, parity, **event_data):
        self.stat['rx_counter'] += 1
        self.rx_link.signal(producer=self.rx_link, byte=byte, parity=parity)


class UARTLink(DSComponent):
    ''' This class represents an UART peripheral in a controller.

    It is simplified peripheral working on basic link layer
    (a typical UART peripheral because UART is defined mostly up to
    link layer only). The peripheral is capable of data transmission
    and receive. It has a buffer of characters to send and buffer
    for receive.

    The TX and RX interfaces are not separated. The reason is that
    typically an UART peripheral has the single settings for both
    RX and TX, i.e. they share the same baudrate for instance.

    Note that the underlying physical peripheral can be selected.
    '''

    def __init__(self,
                 baudrate=115200,
                 bits=8,
                 stopbit=1.5,
                 startbit=1,
                 parity='N',
                 tx_buffer_size=1,
                 rx_buffer_size=1,
                 phys_component=None,  # None (no component) or True (auto create) or component
                 **kwargs
                 ):
        super().__init__(**kwargs)
        self.bits_per_byte = get_bits_per_byte(bits, stopbit, startbit, parity)
        self.parity = parity

        self.bits = bits
        self.stopbit = stopbit
        self.startbit = startbit
        self.parity = parity

        if phys_component is None:
            self.phys = None
            # Link layer does not have timing (it defines only how the bits are created into bytes)
            # But we initialized with baudrate anyway- in the case physical layer is missing
            self.bytetime = self.bits_per_byte / baudrate
            self.transmitting = False  # Flag if we are transmitting now
        elif phys_component:
            self.phys = UARTPhysBasic(
                baudrate,
                bits,
                stopbit,
                startbit,
                parity,
                name=self.name + '.phys',
                sim=self.sim,
            )
        else:
            self.phys = phys_component

        self.tx_buffer_size = tx_buffer_size
        self.tx_buffer = []
        self.tx_buffer_watermark = 1  # invoke irq when there is 1 byte in the buffer

        self.rx_buffer_size = rx_buffer_size
        self.rx_buffer = []
        self.rx_buffer_watermark = rx_buffer_size  # invoke irq when the buffer is full

        self.__add_tx_pubsub()
        self.__add_rx_pubsub()

        self.stat = {}
        self.stat['tx_counter'] = 0  # TX bytes counter
        self.stat['rx_counter'] = 0  # RX bytes counter
        self.stat['err_underrun'] = 0  # TX underrun counter (app too fast to send)
        self.stat['err_overrun'] = 0  # RX overruns counter (app to slow to recv)
        self.stat['err_parity'] = 0  # RX parity error counter
        self.stat['err_other'] = 0  # RX other error counter

    def __add_tx_pubsub(self):
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)
        self.tx_irq = DSProducer(name=self.name + '.tx_irq', sim=self.sim)
        consumer = DSCallback(self._on_tx_event,
                              name=self.name + '.(internal) tx_fb',
                              sim=self.sim
                              )
        if self.phys:
            self.phys.tx_link.add_subscriber(consumer)
        else:
            self.tx.add_subscriber(consumer)

    def __add_rx_pubsub(self):
        self.rx = DSCallback(self._on_rx_event, name=self.name + '.rx', sim=self.sim)
        self.rx_irq = DSProducer(name=self.name + '.rx_irq', sim=self.sim)
        if self.phys:
            self.phys.rx_link.add_subscriber(self.rx)

    def set_tx_watermark(self, watermark):
        ''' Set watermark for the TX buffer to produce IRQ '''
        self.tx_buffer_watermark = watermark

    def send(self, *data):
        ''' Send data to line or to buffer '''
        total = 0
        for byte in data:
            num = 0
            if len(self.tx_buffer) >= self.tx_buffer_size:
                self.stat['err_underrun'] += 1
                continue
            if len(self.tx_buffer) == 0:
                # send the char immediately
                num = self._send_now(byte)
            if not num:
                self.tx_buffer.append(byte)
                num = 1
            total += num
        return total

    @DSSchedulable
    def send_late(self, *data):
        ''' Send data in the future '''
        return self.send(*data)

    def recv(self):
        ''' Get data from buffer '''
        if len(self.rx_buffer) == 0:
            return None
        return self.rx_buffer.pop(0)

    @DSSchedulable
    def recv_late(self):
        ''' Get data from buffer in the future '''
        return self.recv()

    def set_rx_watermark(self, watermark):
        ''' Set watermark for the RX buffer to produce IRQ '''
        self.rx_buffer_watermark = watermark

    def _compute_parity(self, byte):
        ''' Compute a parity bit for the byte  '''
        if self.parity == 'E':
            parity_bit = ParityComputer.compute_byte_parity(byte, even=True)
        elif self.parity == 'O':
            parity_bit = ParityComputer.compute_byte_parity(byte, even=False)
        else:
            parity_bit = None
        return parity_bit

    def _send_now(self, byte):
        ''' This is a handler for the link layer emulation of the UART peripheral.

        This handler works with read bytes and parity bits.
        Though the handler works on link layer, an easy physical layer is also
        implemented by considering timing of physical layer.
        '''
        parity = self._compute_parity(byte)
        if self.phys is None:
            if self.transmitting:
                num = 0
            else:
                self.tx.schedule(self.bytetime, byte=byte, parity=parity)
                self.transmitting = True
                num = 1
        else:
            num = self.phys.send(byte, parity)
        return num

    def _on_tx_event(self, producer, **other):
        ''' Internal feedback after byte was sent  '''
        if not self.phys:
            self.transmitting = False
        # increase statistics
        self.stat['tx_counter'] += 1
        send_watermark = False
        while len(self.tx_buffer) > 0:
            # push chars in buffer if possible
            num = self._send_now(byte=self.tx_buffer[0])
            if not num:
                break
            self.tx_buffer.pop(0)
            if len(self.tx_buffer) == self.tx_buffer_watermark:
                send_watermark = True
        if send_watermark:
            self.tx_irq.signal(producer=producer, flag='byte', flag_detail='sent')
        return False  # allow others to receive TX signal

    def _on_rx_event(self, producer, byte, parity, **other):
        ''' Internal feedback after byte was received  '''
        # Remove previous flag and possible missing parity
        parity_bit = self._compute_parity(byte)
        if parity != parity_bit:
            self.stat['err_parity'] += 1
            self.rx_irq.signal(
                producer=producer,
                flag='err',
                flag_detail='parity',
                byte=byte,
                **other
            )
        elif len(self.rx_buffer) >= self.rx_buffer_size:
            self.stat['err_overrun'] += 1
            self.rx_irq.signal(producer=producer, flag='err', flag_detail='overrun')
        else:
            self.rx_buffer.append(byte)
            self.stat['rx_counter'] += 1
            if len(self.rx_buffer) == self.rx_buffer_watermark:
                self.rx_irq.signal(producer=producer, flag='byte', flag_detail='received')
