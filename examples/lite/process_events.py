# Copyright 2026- majvan (majvan@gmail.com)
#
# The pubsub/process_events.py example is already ported as process_events_lite.py.
# This compatibility entry keeps the same basename in examples/lite.
import runpy
from pathlib import Path


if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('process_events_lite.py')), run_name='__main__')
