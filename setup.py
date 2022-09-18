#!/usr/bin/env python3

from setuptools import find_packages, setup

requirements = [
    "aiohttp",  # Async HTTP requests
    "requests",  # Synchronous HTTP requests
    "matplotlib",  # for plotting figures
    "behave"  # for Behavior-Driven Development (BDD)
]

setup(name='dash-emulator',
      version='0.2.0.dev16',
      description='A headless player to emulate the playback of MPEG-DASH streams',
      author='Yang Liu',
      author_email='yang.jace.liu@linux.com',
      url='https://github.com/Yang-Jace-Liu/dash-emulator-quic',
      packages=find_packages(),
      scripts=["scripts/dash-emulator.py", "scripts/dash-emulator-analyze.py"],
      # install_requires=requirements,
      include_package_data=True,
      package_data={'': ['resources/*']}
      )
