# Copyright 2021 NXP Semiconductors
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
A queue of events with runtime flexibility of put / get events.
'''
from dssim.simulation import DSComponent

class Queue(DSComponent):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, *args, **kwargs):
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.queue = []
        self.waiting_tasks = []

    def put(self, **event):
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        if not self.waiting_tasks:
            self.queue.append(event)
        else:
            self.sim.signal(self.waiting_tasks[0], **event)

    def get(self, timeout=float('inf')):
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        if len(self.queue) > 0:
            return self.queue.pop(0)
        self.waiting_tasks.append(self.sim.parent_process)
        try:
            obj = yield from self.sim.wait(timeout, cond=lambda c:True)
        finally:
            try:
                waiting_task = self.waiting_tasks.remove(self.sim.parent_process)
            except ValueError as e:
                pass
        return obj

    def __len__(self):
        return len(self.queue)
