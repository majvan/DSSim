# Copyright 2020- majvan (majvan@gmail.com)
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
Time queue module facade.

Alternative implementations are also exported for explicit selection.
'''

from dssim.timequeue.base import ITimeQueue
from dssim.timequeue.bintree import TQBinTree, NowQueue
from dssim.timequeue.bisect import TQBisect

__all__ = [
    'NowQueue',
    'ITimeQueue',
    'TQBinTree',
    'TQBisect',
]
