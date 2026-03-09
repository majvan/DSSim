from tests.test_interface import TestInterface
from tests.test_timequeue import TestTimeQueue
from tests.test_pubsub import TestCallback, TestSubscriber, TestProducer
from tests.test_simulation import TestSim, TestScheduleEventNow
from tests.test_process import TestDSSchedulable, TestException, TestConditionChecking, TestDSProcessAbort
from tests.test_process_mixin import TestSim as TestSimProcessMixin, TestDSProcessAbort as TestDSProcessAbortMixin
from tests.test_queue import TestDSQueue, TestDSLifoQueue, TestDSKeyQueue, TestQueue
# from tests.test_event import TestEvent
import unittest

if __name__ == '__main__':
    unittest.main()
