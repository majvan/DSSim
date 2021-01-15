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
from pathlib import Path
from setuptools import setup, find_packages


ROOT = Path(__file__).resolve().parent


def read_requirements() -> list[str]:
    req_path = ROOT / 'requirements.txt'
    if not req_path.exists():
        return []
    reqs = []
    for line in req_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        reqs.append(line)
    return reqs


def read_version() -> str:
    init_py = (ROOT / 'dssim' / '__init__.py').read_text(encoding='utf-8')
    for line in init_py.splitlines():
        if line.startswith('__version__ = '):
            return line.split('=', 1)[1].strip().strip("'\"")
    raise RuntimeError('Unable to find __version__ in dssim/__init__.py')


setup(
    name='dssim',
    version=read_version(),
    license='Apache-2.0',
    description='Discrete-event simulation framework',
    long_description=(ROOT / 'README.md').read_text(encoding='utf-8'),
    long_description_content_type='text/markdown',
    author='majvan',
    author_email='juraj.vanco@nxp.com',
    url='https://github.com/majvan/dssim',
    project_urls={
        'Documentation': 'https://majvan.github.io/DSSim/',
        'Source': 'https://github.com/majvan/dssim',
        'Bug Tracker': 'https://github.com/majvan/dssim/issues',
    },
    keywords=['simulation', 'simulator', 'discrete', 'system', 'event', 'process', 'event-based', 'time'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development',
    ],
    python_requires='>=3.10',
    install_requires=read_requirements(),
    packages=find_packages(exclude=('tests', 'tests.*', 'benchmarks', 'benchmarks.*')),
    include_package_data=True,
)
