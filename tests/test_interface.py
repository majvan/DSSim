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
Tests for instance module
'''
import unittest
from dssim.simulation import DSComponent

class MyComponent(DSComponent):
    pass

class TestInterface(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def test0_simple_event(self):
        ''' Assert kicking and pushing events '''
        i0 = MyComponent()
        name = list(MyComponent._names.keys())[0]
        with self.assertRaises(ValueError):
            i1 = MyComponent(name=name)
        i2 = MyComponent(name='xyz')
        self.assertEqual(str(i2), 'xyz')

