#!/usr/bin/env python3

from setuptools import find_packages, setup

requirements = [
    "wsproto",
    "uvloop",
    "aiohttp",
    "requests",
    "matplotlib",
    "behave",
    "aioquic==0.9.11dev2",
    "matplotlib",
    "pyyaml",
    "sslkeylog"
]

setup(name='dash-emulator-quic',
      version='0.2.0.dev0',
      description='A headless player to emulate the playback of MPEG-DASH streams over QUIC',
      author='Yang Liu',
      author_email='yang.jace.liu@linux.com',
      url='https://github.com/Yang-Jace-Liu/dash-emulator-quic',
      packages=find_packages(),
      scripts=["scripts/dash-emulator.py", "scripts/dash-emulator-analyze.py"],
      install_requires=requirements,
      include_package_data=True,
      package_data={'': ['resources/*']}
      )
