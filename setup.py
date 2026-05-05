# Source - https://stackoverflow.com/a/69673312
# Posted by IcyIcicle
# Retrieved 2026-04-28, License - CC BY-SA 4.0

from setuptools import setup

APP = ['traintime.py'] # points to your main python file
DATA_FILES = ['stations.json']
OPTIONS = {
    'packages': ['pynput'] # include your other dependencies here
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
