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
'''
Tests for simulation module
'''
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock, call
from dssim import DSSimulation, DSFuture, DSAbortException

class SimMockWithObserveContext(Mock):
    def __init__(self, *args, **kwargs):
        self.registered_endpoints = []

    def observe_pre(self, endpoint):
        self.registered_endpoints.append(endpoint)
        return contextmanager(None)

class FutureMock(Mock):
    def get_eps(self):
        return {self,}

class TestDSFuture(unittest.TestCase):

    def test1_future_eps(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        endpoints = fut.get_eps()
        self.assertEqual(endpoints, {fut._finish_tx})
    
    def test2_future_finish(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.finish('hello')
        self.assertEqual(fut.value, 'hello')
        self.assertEqual(fut.exc, None)
        finish = fut.finished()
        self.assertTrue(finish)

    def test3_future_fail(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.fail('hello')
        self.assertEqual(fut.value, None)
        self.assertEqual(fut.exc, 'hello')
        finish = fut.finished()
        self.assertTrue(finish)

    def test4_future_send(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.send('hello')
        self.assertEqual(fut.value, 'hello')
        self.assertEqual(fut.exc, None)
        finish = fut.finished()
        self.assertTrue(finish)

    def test5_future_abort(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.abort()
        self.assertTrue(isinstance(fut.value, DSAbortException))
        finish = fut.finished()
        self.assertTrue(finish)

    def test6_future_await_already_finished(self):
        sim = MagicMock()
        fut = DSFuture(sim=sim)
        fut.finish('hello')
        process = fut.__await__()
        try:
            next(process)  # future already finished => no wait, should stop immediately
            self.assertTrue(False)  # should not be here
        except StopIteration as e:
            retval = e.value
        self.assertIsNone(retval)  # already finished: gwait skipped, retval stays None
        sim.gwait.assert_not_called()

    def test7_future_await_not_finished(self):
        sim = MagicMock()
        fut = DSFuture(sim=sim)
        process = fut.__await__()
        sim.gwait.assert_not_called()
        try:
            process.send(None)  # sim.gwait is a MagicMock (not a generator) => StopIteration raised
            self.assertTrue(False)  # should not be here
        except StopIteration as e:
            retval = e.value
        sim.gwait.assert_called_once_with(cond=fut)
        self.assertIsNone(retval)