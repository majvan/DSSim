#!/usr/bin/env sh

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
PYTHONPATH="$SCRIPT_DIR/.."

echo "Process schedule"
python $SCRIPT_DIR/process_schedule.py
echo "Process return value"
python $SCRIPT_DIR/process_retval.py
echo "Consumer ordering (default, round robin, priority...)"
python $SCRIPT_DIR/consumer_ordering.py
echo "Running bottleneck"
python $SCRIPT_DIR/bottleneck.py
echo "Running bottleneck controller"
python $SCRIPT_DIR/bottleneck_controller.py
echo "Running circuits callback"
python $SCRIPT_DIR/circuits_callback.py
echo "Running conditions"
python $SCRIPT_DIR/conditions.py
echo "Running conditions generator"
python $SCRIPT_DIR/conditions_generator.py
echo "Running conditions async"
python $SCRIPT_DIR/conditions_async.py
echo "Running conditions futures"
python $SCRIPT_DIR/conditions_futures.py
echo "Running conditions process"
python $SCRIPT_DIR/conditions_process.py
echo "Running gas station"
python $SCRIPT_DIR/gasstation.py
echo "Running interruptible context"
python $SCRIPT_DIR/interruptible_context.py
#   echo "I2C loopback"
#   python $SCRIPT_DIR/i2c_master_slave.py
echo "Processcomponent"
python $SCRIPT_DIR/processcomponent.py
echo "Queue"
python $SCRIPT_DIR/queue.py
echo "School"
python $SCRIPT_DIR/school.py
echo "Studio"
python $SCRIPT_DIR/studio.py
echo "UART physical"
python $SCRIPT_DIR/uart_physical.py
echo "VISA check"
python $SCRIPT_DIR/visa_check.py
# The following are benchmark tests which take some time
echo "Process events"
python $SCRIPT_DIR/process_events.py
echo "UART loop"
python $SCRIPT_DIR/uart_loop.py

echo "Asyncio chained"
python $SCRIPT_DIR/asyncio/chained.py
echo "Asyncio count"
python $SCRIPT_DIR/asyncio/countasync.py
echo "Asyncio rand"
python $SCRIPT_DIR/asyncio/rand.py
echo "Asyncio task"
python $SCRIPT_DIR/asyncio/test_asyncio_task.py
echo "Asyncio taskgroup"
python $SCRIPT_DIR/asyncio/test_asyncio_taskgroup.py
echo "Asyncio cancel"
python $SCRIPT_DIR/asyncio/test_cancel.py
echo "Asyncio future"
python $SCRIPT_DIR/asyncio/test_future.py
echo "Asyncio gather"
python $SCRIPT_DIR/asyncio/test_gather.py
echo "Asyncio timeout"
python $SCRIPT_DIR/asyncio/test_timeout.py
