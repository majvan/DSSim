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
An event which can unblock many waiting tasks upon its signal.
'''
from dssim.simulation import DSComponent

class Event(DSComponent):
    ''' A software event with binary state (signalled / clear).
    A task can be blocked by waiting for the event signalled state.
    '''

    def __init__(self, *args, **kwargs):
        ''' Init Event component. An event being signalled unblocks tasks waiting
        for the event.
        If the event is signalled, a task going to wait is unblocked immediately.
        '''
        super().__init__(*args, **kwargs)
        self._tx = DSProducer(name=self.name + '.tx (internal)', sim=self.sim)

    def signal(self):
        ''' Signal the event and unblocks all the tasks waiting for it. '''
        self._tx.signal({})


    def clear(self):
        ''' Clear the event '''
        self.signalled = False

    async def wait(self, timeout=float('inf')):
        ''' Wait till event is signalled. If the event is already signalled, return immediately. '''
        if self.signalled:
            return True
        self.waiting_tasks.append(self.sim.parent_process)
        with self.sim.monitor(self._tx):
            obj = await self.sim.wait(timeout, cond=lambda e:True)
        return obj
