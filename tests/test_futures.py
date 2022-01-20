# Copyright 2020 NXP Semiconductors
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
    def get_future_eps(self):
        return {self,}

class TestDSFuture(unittest.TestCase):

    def test0_future_eps(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        endpoints = fut.get_future_eps()
        self.assertEqual(endpoints, {fut._finish_tx})
    
    def test1_future_finish(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.finish('hello')
        self.assertEqual(fut.value, 'hello')
        self.assertEqual(fut.exc, None)
        finish = fut.finished()
        self.assertTrue(finish)

    def test2_future_fail(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.fail('hello')
        self.assertEqual(fut.value, None)
        self.assertEqual(fut.exc, 'hello')
        finish = fut.finished()
        self.assertTrue(finish)

    def test3_future_send(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.send('hello')
        self.assertEqual(fut.value, 'hello')
        self.assertEqual(fut.exc, None)
        finish = fut.finished()
        self.assertTrue(finish)

    def test4_future_abort(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        finish = fut.finished()
        self.assertFalse(finish)
        fut.abort()
        self.assertTrue(isinstance(fut.value, DSAbortException))
        finish = fut.finished()
        self.assertTrue(finish)

    def test5_future_gwait(self):
        def wait_for_future(fut, timeout):
            yield from fut.gwait(timeout)
            return 'done'
        sim = MagicMock()
        fut = DSFuture(sim=sim)
        fut.finish('hello')
        process = wait_for_future(fut, 10)
        try:
            retval = next(process)  # future finished => no wait
            self.assertTrue(False)  # this shoould not be here
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'done')
        sim.gwait.assert_not_called()

        fut = DSFuture(sim=sim)
        process = wait_for_future(fut, 10)
        sim.gwait.assert_not_called()
        try:
            retval = process.send(None)  # sim.wait is not now a generator, it is a mocked method => StopIteration is called
            self.assertTrue(False)  # this shoould not be here
        except StopIteration as e:
            retval = e.value
        sim.gwait.assert_called_once_with(10, cond=fut)
        self.assertTrue(retval == 'done')

    def test6_future_wait(self):
        async def wait_for_future(fut, timeout):
            await fut.wait(timeout)
            return 'done'
        sim = MagicMock()
        fut = DSFuture(sim=sim)
        fut.finish('hello')
        process = wait_for_future(fut, 10)
        try:
            retval = process.send(None)  # future finished => no wait
            self.assertTrue(False)  # this shoould not be here
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'done')
        sim.gwait.assert_not_called()

        sim = MagicMock()
        fut = DSFuture(sim=sim)
        process = wait_for_future(fut, 10)
        sim.wait.assert_not_called()
        # Unfortunately, the following cannot be easily tested:
        # It is impossible to await MagicMock. AsyncMock could be used,
        # but it is impossible to have a context manager with AsyncMock.
        # try:
        #     retval = process.send(None)  
        #     self.assertTrue(False)  # this shoould not be here
        # except StopIteration as e:
        #     retval = e.value
        # sim.wait.assert_called_once_with(10, cond=fut)
        # self.assertTrue(retval == 'done')