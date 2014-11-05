#!/usr/bin/env python

from distutils.core import setup

setup(name='linodefs',
        version='0.1',
        description='FUSE-based filesystem for accessing Linode resources',
        author='Marques Johansson',
        author_email='marques@displague.com',
        url='https://github.com/displague/linodefs',
        scripts=['linodefs.py',],
        )

