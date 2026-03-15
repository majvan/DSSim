# Copyright 2022- majvan (majvan@gmail.com)
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
The salabim-like API export.
'''
from dssim import DSSimulation, DSComponent as component
from dssim import DSSchedulable, DSProcess, DSCallback, DSAbortException
from dssim import DSPub, DSFilter
from dssim.pubsub.agent import DSAgent as Component
from dssim.pubsub.agent import PCGenerator as ComponentGenerator

from dssim.pubsub.components.container import DSContainer as Store
from dssim.pubsub.components.container import DSContainer
from dssim.pubsub.components.queue import DSQueue
from dssim.pubsub.components.resource import DSResource, DSPriorityResource
from dssim.pubsub.components.state import DSState

class Environment(DSSimulation):
    def now(self):
        return self.time


# Lowercase constructor aliases keep salabim-like examples concise and
# align with factory-style naming used across DSSim examples.
queue = DSQueue
container = DSContainer
resource = DSResource
priority_resource = DSPriorityResource
state = DSState
