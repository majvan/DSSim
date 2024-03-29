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
from dssim import DSSchedulable, DSProcess, DSCallback, DSAbsTime, DSAbortException
from dssim import DSProducer, DSFilter
from dssim.processcomponent import DSProcessComponent as Component
from dssim.processcomponent import PCGenerator as ComponentGenerator

from dssim.components.container import Container as Store, Queue
from dssim.components.resource import Resource
from dssim.components.state import State

class Environment(DSSimulation):
    def now(self):
        return self.time
