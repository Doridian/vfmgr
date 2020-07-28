from yaml import load as yaml_load, dump as yaml_dump

CONFIG = None

LXC_DIR = '/etc/pve/lxc/'
QEMU_DIR = '/etc/pve/qemu-server/'

def load():
    global CONFIG

    f = open('config.yml', 'r')
    CONFIG = yaml_load(f)
    f.close()

def save():
    global CONFIG

    d = yaml_dump(CONFIG)
    f = open('config.yml', 'w')
    f.write(d)
    f.close()

load()
