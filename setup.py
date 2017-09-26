#!/usr/bin/env python

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('requirements.txt', 'r') as f:
    requirements = list(filter(None, (line.strip() for line in f)))

with open('VERSION', 'r') as f:
    version = f.read().strip()

setup(
    name='ycsettings',
    version=version,
    description="A utility module for handling app settings.",
    long_description=readme,
    author="Yanchuan Sim",
    author_email='yanchuan@outlook.com',
    url='https://github.com/skylander86/ycsettings',
    packages=find_packages(include=['ycsettings']),
    install_requires=requirements,
    license="Apache Software License 2.0",
    zip_safe=True,
    keywords='ycsettings',
    test_suite='ycsettings.test',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
)
