#!/usr/bin/env python3

from distutils.core import setup

from setuptools import find_packages

requirements = [
    "wsproto",
    "uvloop",
    "aiohttp",
    "requests",
    "matplotlib",
    "behave",
    "aioquic",
    "dash-emulator @ git+https://github.com/yang-jace-liu/dash-emulator#egg=dash-emulator"
]

setup(name='dash-emulator-quic',
      version='0.2.0.dev0',
      description='A headless player to emulate the playback of MPEG-DASH streams over QUIC',
      author='Yang Liu',
      author_email='yang.jace.liu@linux.com',
      url='https://github.com/Yang-Jace-Liu/dash-emulator-quic',
      packages=find_packages(),
      scripts=["scripts/dash-emulator.py"],
      install_requires=requirements
      )
