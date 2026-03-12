from setuptools import setup

setup(
    name='speedsearch',
    version='1.0.0',
    author='AD2011',
    description='Ookla SpeedTest CLI wrapper with server search features',
    python_requires='>=3.6',
    install_requires=[
        'requests',
        'prompt-toolkit',
    ],
    entry_points={
        'console_scripts': [
            'speedsearch=speedsearch:main',
        ],
    },
)