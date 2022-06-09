#!/usr/bin/env sh

CURRENT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
PYTHONPATH="$CURRENT_DIR/.."

echo "Process schedule"
python ./process_schedule.py
echo "Running bottleneck"
python ./bottleneck.py
#  echo "Running bottleneck controller"
#  python ./bottleneck_controller.py
echo "Running conditions"
python ./conditions.py
echo "Running conditions process"
python ./conditions_process.py
echo "Running gas station"
python ./gasstation.py
#   echo "I2C loopback"
#   python ./i2c_master_slave.py
#   echo "Process events"
#   python ./process_events.py
echo "Processcomponent"
python ./processcomponent.py
echo "Queue"
python ./queue.py
echo "School"
python ./school.py
echo "Studio"
python ./studio.py
#   echo "UART loop"
#   python ./uart_loop.py
#   echo "UART physical"
#   python ./uart_physical.py
echo "VISA check"
python ./visa_check.py
