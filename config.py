from yaml import load as yaml_load, dump as yaml_dump
from os.path import dirname, abspath

CONFIG = None

SCRIPT_DIR = dirname(abspath(__file__))
CONFIG_FILE = f'{SCRIPT_DIR}/config.yml'

LXC_DIR = '/etc/pve/lxc/'
QEMU_DIR = '/etc/pve/qemu-server/'

def load():
    global CONFIG

    f = open(CONFIG_FILE, 'r')
    CONFIG = yaml_load(f)
    f.close()

def save():
    global CONFIG

    d = yaml_dump(CONFIG)
    f = open(CONFIG_FILE, 'w')
    f.write(d)
    f.close()

load()
