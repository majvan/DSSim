#!/usr/bin/env sh

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
PYTHONPATH="$SCRIPT_DIR/.."

echo "Process schedule"
python $SCRIPT_DIR/process_schedule.py
echo "Running bottleneck"
python $SCRIPT_DIR/bottleneck.py
echo "Running bottleneck controller"
python $SCRIPT_DIR/bottleneck_controller.py
echo "Running conditions"
python $SCRIPT_DIR/conditions.py
echo "Running conditions process"
python $SCRIPT_DIR/conditions_process.py
echo "Running gas station"
python $SCRIPT_DIR/gasstation.py
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
#   echo "UART loop"
#   python $SCRIPT_DIR/uart_loop.py
echo "UART physical"
python $SCRIPT_DIR/uart_physical.py
echo "VISA check"
python $SCRIPT_DIR/visa_check.py
# The following are benchmark tests which take some time
echo "Process events"
python $SCRIPT_DIR/process_events.py
