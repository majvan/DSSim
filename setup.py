# Copyright 2020 NXP Semiconductors
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
from distutils.core import setup
from setuptools import setup, find_packages

with open('requirements.txt', 'r') as req_lines:
    all_requires = req_lines.read().splitlines()

setup(
  name='dssim',
  version='0.1',  # Before going to 1.0, we need public review
  license ='apache-2.0',  # The keyword taken from here: https://help.github.com/articles/licensing-a-repository
  description='Discrete System Simulation framework',
  long_description='A simulation framework to simulate time-based discrete '
      'events. Useful to simulate behavior of a digital system in time.', # This can be moved into separate desc file in the future
  author='NXP Semiconductors',
  author_email='juraj.vanco@nxp.com',
  url='https://github.com/majvan/dssim',   # Provide either the link to your github or to your website
  keywords=['simulation', 'simulator', 'discrete', 'system', 'event', 'Process', 'event-based', 'time'],   # Keywords that define your package best
  classifiers=[
    'Development Status :: 3 - Alpha', # "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of the package
    'Intended Audience :: Developers',
    'Topic :: Software Development',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python :: 3',
  ],
  install_requires=all_requires,
  packages=find_packages(),
)
