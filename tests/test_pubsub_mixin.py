# Copyright 2020- majvan (majvan@gmail.com)
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
Tests for SimPubsubMixin factory methods: sim.producer(), sim.callback(),
sim.kw_callback().
'''
import unittest
from unittest.mock import Mock
from dssim import DSSimulation, DSProducer, DSCallback, DSKWCallback


class TestSimPubsubMixin(unittest.TestCase):

    def test1_producer_factory_returns_dsproducer(self):
        sim = DSSimulation()
        p = sim.producer(name='test_producer')
        self.assertIsInstance(p, DSProducer)
        self.assertIs(p.sim, sim)

    def test2_producer_factory_rejects_foreign_sim(self):
        sim = DSSimulation()
        other_sim = DSSimulation(single_instance=False)
        with self.assertRaises(ValueError):
            sim.producer(name='x', sim=other_sim)

    def test3_callback_factory_returns_dscallback(self):
        sim = DSSimulation()
        fn = Mock()
        cb = sim.callback(fn)
        self.assertIsInstance(cb, DSCallback)
        self.assertIs(cb.sim, sim)

    def test4_callback_factory_forwards_call(self):
        sim = DSSimulation()
        fn = Mock(return_value=True)
        cb = sim.callback(fn)
        cb.send({'x': 1})
        fn.assert_called_once_with({'x': 1})

    def test5_callback_factory_rejects_foreign_sim(self):
        sim = DSSimulation()
        other_sim = DSSimulation(single_instance=False)
        with self.assertRaises(ValueError):
            sim.callback(Mock(), sim=other_sim)

    def test6_kw_callback_factory_returns_dskwcallback(self):
        sim = DSSimulation()
        fn = Mock()
        cb = sim.kw_callback(fn)
        self.assertIsInstance(cb, DSKWCallback)
        self.assertIs(cb.sim, sim)

    def test7_kw_callback_factory_unpacks_dict_as_kwargs(self):
        sim = DSSimulation()
        fn = Mock(return_value=True)
        cb = sim.kw_callback(fn)
        cb.send({'a': 1, 'b': 2})
        fn.assert_called_once_with(a=1, b=2)

    def test8_kw_callback_factory_rejects_foreign_sim(self):
        sim = DSSimulation()
        other_sim = DSSimulation(single_instance=False)
        with self.assertRaises(ValueError):
            sim.kw_callback(Mock(), sim=other_sim)


if __name__ == '__main__':
    unittest.main()
