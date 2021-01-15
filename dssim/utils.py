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
Provide math functions and classes for various digital system needs
'''
from binascii import crc32 as crc32lib, crc_hqx

class ParityComputer:
    ''' Computes a parity over numbers. The class is singleton, i.e. it should not
    be instantiated. Class methods are used without class instances.
    '''
    @classmethod
    def _compute_lookup(cls, i):
        ''' Compute a lookup table for fast parity calculation.
        The code is taken from http://p-nand-q.com/python/algorithms/math/bit-parity.html
        '''
        i = i - ((i >> 1) & 0x55555555)
        i = (i & 0x33333333) + ((i >> 2) & 0x33333333)
        i = (((i + (i >> 4)) & 0x0F0F0F0F) * 0x01010101) >> 24
        return i & 0x01

    @classmethod
    def compute_parity(cls, dword, even=True):
        ''' Compute a parity of 32b. dword
        The code is taken from http://p-nand-q.com/python/algorithms/math/bit-parity.html
        '''
        dword ^= dword >> 16
        dword ^= dword >> 8
        retval = ParityComputer._lookup[dword & 0xff]
        if not even:
            retval ^= 0x01
        return retval

    @classmethod
    def compute_byte_parity(cls, byte, even=True):
        ''' Compute a parity of 8b. byte
        The code is taken from http://p-nand-q.com/python/algorithms/math/bit-parity.html
        '''
        retval = ParityComputer._lookup[byte]
        if not even:
            retval ^= 0x01
        return retval

    @classmethod
    def compute_byte_even_parity(cls, byte):
        ''' Compute a bit to form with byte an even parity
        The code is taken from http://p-nand-q.com/python/algorithms/math/bit-parity.html
        '''
        return ParityComputer._lookup[byte]

    @classmethod
    def compute_byte_odd_parity(cls, byte):
        ''' Compute a bit to form with byte an odd parity
        The code is taken from http://p-nand-q.com/python/algorithms/math/bit-parity.html
        '''
        return ParityComputer._lookup[byte] ^ 0x01

# Precompute the ParityComputer table
ParityComputer._lookup = [ParityComputer._compute_lookup(i) for i in range(256)]


class CRCComputer:
    ''' Compute CRC for a bytearray / bytes '''

    def __init__(self, *data):
        if not isinstance(data, bytes):
            self.data = bytes(data)
        else:
            self.data = data

    def crc32(self):
        ''' Compute CRC-32 over initiated data '''
        return crc32lib(self.data)

    def crc16(self):
        ''' Compute CRC-16 over initiated data '''
        return crc_hqx(self.data, 0)


class ByteAssembler:
    ''' Machine which transfers stream of bits into an int '''
    def __init__(self, bits=None):
        self.bits = bits or bytearray(bits)

    def get(self, bits_in_result=None, lsb=True):
        ''' Computes the integer from streams of bits.
        If the input bits does not have all the bits required, then the number of bits is taken
        from the input and the missing bits are expected to have a value of 0.
        '''
        bits_in_result = bits_in_result or len(self.bits)
        if len(self.bits) > bits_in_result:
            raise ValueError('Number of final bits in result is less than provided (lose of info).')
        result = 0
        if lsb:
            missing_bits = bits_in_result - len(self.bits)
            bits = [0] * missing_bits + list(reversed(self.bits))
            for bit in bits:
                result <<= 1
                result += bit
        else:
            for i, bit in enumerate(self.bits):
                if i >= bits_in_result:
                    break
                result <<= 1
                result += bit
        return result
