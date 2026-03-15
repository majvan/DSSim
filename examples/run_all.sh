#!/usr/bin/env sh

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
export PYTHONPATH="$SCRIPT_DIR/.."

if command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
else
    echo "No python interpreter found (python/python3)." >&2
    exit 1
fi

run_py() {
    echo "$1"
    "$PYTHON_BIN" "$2"
}

echo "Lite layer examples"
run_py "Coro schedule" "$SCRIPT_DIR/lite/coro_schedule.py"
run_py "Lite process events" "$SCRIPT_DIR/lite/process_events.py"
run_py "Lite queue" "$SCRIPT_DIR/lite/queue.py"
run_py "Lite trajectory" "$SCRIPT_DIR/lite/trajectory.py"
run_py "Lite time delay" "$SCRIPT_DIR/lite/time_delay.py"
run_py "Lite time limiter" "$SCRIPT_DIR/lite/time_limiter.py"
run_py "Lite time timer" "$SCRIPT_DIR/lite/time_timer.py"
run_py "Lite demo wait (signal)" "$SCRIPT_DIR/lite/Demo wait (signal).py"
run_py "Lite agent" "$SCRIPT_DIR/lite/agent.py"
run_py "Lite school" "$SCRIPT_DIR/lite/school.py"
run_py "Lite gas station" "$SCRIPT_DIR/lite/gasstation.py"
run_py "Lite priority resource" "$SCRIPT_DIR/lite/priority_resource.py"
run_py "Lite priority resources nested" "$SCRIPT_DIR/lite/priority_resources_nested.py"
run_py "Lite visa check" "$SCRIPT_DIR/lite/visa_check.py"
run_py "Lite bank, 1 clerk" "$SCRIPT_DIR/lite/Bank, 1 clerk.py"
run_py "Lite bank, 3 clerks" "$SCRIPT_DIR/lite/Bank, 3 clerks.py"
run_py "Lite bank, 3 clerks (resources)" "$SCRIPT_DIR/lite/Bank, 3 clerks (resources).py"
run_py "Lite bank, 3 clerks (with ComponentGenerator)" "$SCRIPT_DIR/lite/Bank, 3 clerks (with ComponentGenerator).py"
run_py "Lite bank, 3 clerks reneging (resources)" "$SCRIPT_DIR/lite/Bank, 3 clerks reneging (resources).py"

echo "PubSub layer examples"
run_py "Process schedule" "$SCRIPT_DIR/pubsub/process_schedule.py"
run_py "Process return value" "$SCRIPT_DIR/pubsub/process_retval.py"
run_py "Consumer ordering (default, round robin, priority...)" "$SCRIPT_DIR/pubsub/consumer_ordering.py"
run_py "Running bottleneck" "$SCRIPT_DIR/pubsub/bottleneck.py"
run_py "Running bottleneck controller" "$SCRIPT_DIR/pubsub/bottleneck_controller.py"
run_py "Running circuits callback" "$SCRIPT_DIR/pubsub/circuits_callback.py"
run_py "Running conditions" "$SCRIPT_DIR/pubsub/conditions.py"
run_py "Running conditions generator" "$SCRIPT_DIR/pubsub/conditions_generator.py"
run_py "Running conditions async" "$SCRIPT_DIR/pubsub/conditions_async.py"
run_py "Running conditions futures" "$SCRIPT_DIR/pubsub/conditions_futures.py"
run_py "Running conditions process" "$SCRIPT_DIR/pubsub/conditions_process.py"
run_py "Running gas station" "$SCRIPT_DIR/pubsub/gasstation.py"
run_py "Running interruptible context" "$SCRIPT_DIR/pubsub/interruptible_context.py"
run_py "Agent" "$SCRIPT_DIR/pubsub/agent.py"
run_py "Queue" "$SCRIPT_DIR/pubsub/queue.py"
run_py "Time delay" "$SCRIPT_DIR/pubsub/time_delay.py"
run_py "Time limiter" "$SCRIPT_DIR/pubsub/time_limiter.py"
run_py "Time timer" "$SCRIPT_DIR/pubsub/time_timer.py"
run_py "School" "$SCRIPT_DIR/pubsub/school.py"
run_py "Studio" "$SCRIPT_DIR/pubsub/studio.py"
run_py "Trajectory" "$SCRIPT_DIR/pubsub/trajectory.py"
run_py "UART physical" "$SCRIPT_DIR/pubsub/uart_physical.py"
run_py "UART loop" "$SCRIPT_DIR/pubsub/uart_loop.py"
run_py "Producer to process" "$SCRIPT_DIR/pubsub/producer_to_process.py"
run_py "Priority resource" "$SCRIPT_DIR/pubsub/priority_resource.py"
run_py "Priority resources" "$SCRIPT_DIR/pubsub/priority_resources_combined.py"
run_py "Priority resources nested" "$SCRIPT_DIR/pubsub/priority_resources_nested.py"
run_py "Priority resources parity (pubsub)" "$SCRIPT_DIR/pubsub/PriorityResource pubsub.py"

echo "VISA check"
visa_log="$(mktemp)"
i=1
while [ "$i" -le 20 ]; do
    echo "VISA check run $i/20"
    "$PYTHON_BIN" "$SCRIPT_DIR/pubsub/visa_check.py" | tee "$visa_log" | "$PYTHON_BIN" "$SCRIPT_DIR/output_parser/visa_check_parser.py" - || {
        echo "VISA check parser: error found"
        rm -f "$visa_log"
        exit 1
    }
    i=$((i + 1))
done
rm -f "$visa_log"

run_py "Process events" "$SCRIPT_DIR/pubsub/process_events.py"

run_py "Asyncio chained" "$SCRIPT_DIR/pubsub/asyncio/chained.py"
run_py "Asyncio count" "$SCRIPT_DIR/pubsub/asyncio/countasync.py"
run_py "Asyncio rand" "$SCRIPT_DIR/pubsub/asyncio/rand.py"
run_py "Asyncio task" "$SCRIPT_DIR/pubsub/asyncio/test_asyncio_task.py"
run_py "Asyncio taskgroup" "$SCRIPT_DIR/pubsub/asyncio/test_asyncio_taskgroup.py"
run_py "Asyncio cancel" "$SCRIPT_DIR/pubsub/asyncio/test_cancel.py"
run_py "Asyncio future" "$SCRIPT_DIR/pubsub/asyncio/test_future.py"
run_py "Asyncio gather" "$SCRIPT_DIR/pubsub/asyncio/test_gather.py"
run_py "Asyncio timeout" "$SCRIPT_DIR/pubsub/asyncio/test_timeout.py"

echo "PubSub parity examples (simpy-style API via DSSim backend)"
echo "Parity PriorityResource (simpy-style) [backend=dssim]"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/parity/simpy/PriorityResource simpy.py" --backend dssim
echo "Parity process events (simpy-style) [backend=dssim]"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/parity/simpy/process_events_simpy.py" --backend dssim
echo "Parity visa check (simpy-style) [backend=dssim]"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/parity/simpy/visa_check_simpy.py" --backend dssim

run_py "Bank, 1 clerk" "$SCRIPT_DIR/pubsub/Bank, 1 clerk.py"
run_py "Bank, 3 clerks" "$SCRIPT_DIR/pubsub/Bank, 3 clerks.py"
run_py "Bank, 3 clerks (resources)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks (resources).py"
run_py "Bank, 3 clerks (signal)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks (signal).py"
run_py "Bank, 3 clerks (state)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks (state).py"
run_py "Bank, 3 clerks (store)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks (store).py"
run_py "Bank, 3 clerks (with ComponentGenerator)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks (with ComponentGenerator).py"
run_py "Bank, 3 clerks reneging" "$SCRIPT_DIR/pubsub/Bank, 3 clerks reneging.py"
run_py "Bank, 3 clerks reneging (resources)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks reneging (resources).py"
run_py "Bank, 3 clerks reneging (signal)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks reneging (signal).py"
run_py "Bank, 3 clerks reneging (state)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks reneging (state).py"
run_py "Bank, 3 clerks reneging (store)" "$SCRIPT_DIR/pubsub/Bank, 3 clerks reneging (store).py"

echo "Demo wait"
demo_wait_log="$(mktemp)"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/Demo wait.py" | tee "$demo_wait_log" | "$PYTHON_BIN" "$SCRIPT_DIR/output_parser/demo_wait_parser.py" - || {
    echo "Demo wait parser: error found"
    rm -f "$demo_wait_log"
    exit 1
}
echo "Demo wait (mutex)"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/Demo wait (mutex).py" | tee "$demo_wait_log" | "$PYTHON_BIN" "$SCRIPT_DIR/output_parser/demo_wait_parser.py" - || {
    echo "Demo wait parser: error found"
    rm -f "$demo_wait_log"
    exit 1
}
echo "Demo wait (signal)"
"$PYTHON_BIN" "$SCRIPT_DIR/pubsub/Demo wait (signal).py" | tee "$demo_wait_log" | "$PYTHON_BIN" "$SCRIPT_DIR/output_parser/demo_wait_parser.py" - || {
    echo "Demo wait parser: error found"
    rm -f "$demo_wait_log"
    exit 1
}
rm -f "$demo_wait_log"

run_py "Elevator parity sample" "$SCRIPT_DIR/pubsub/Elevator.py"
