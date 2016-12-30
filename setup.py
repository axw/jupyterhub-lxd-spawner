from setuptools import setup

classifiers = [
    "Framework :: IPython",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "Programming Language :: Python",
    "License :: OSI Approved :: MIT License",
    "Development Status :: 4 - Beta",
    "Topic :: System :: Distributed Computing",
]

setup(
    name='lxdspawner',
    version='0.1',
    install_requires=[
        'jupyterhub>=0.4.0',
    ],
    description='JupyterHub Spawner for LXD',
    url='http://github.com/axw/jupyterhub-lxd-spawner',
    author='Andrew Wilkins',
    author_email='axwalk@gmail.com',
    license='MIT',
    classifiers=classifiers,
    packages=['lxdspawner'],
)

