class PVEConfig:
    def __init__(self, file):
        self.file = file
        self.dirty = False

        fh = open(self.file, 'r')
        lines = fh.read().split('\n')
        fh.close()

        self.cfg = {}
        for line in lines:
            if len(line) < 1 or line[0] == '#':
                continue
            lsplit = line.split(': ')
            self.cfg[lsplit[0]] = ': '.join(lsplit[1:])
        
    def save(self):
        print(f'Saving PVE config to {self.file}')

        strData = ''
        for key in self.cfg:
            strData += f'{key}: {self.cfg[key]}\n'
        
        fh = open(self.file, 'w')
        fh.write(strData)
        fh.close()

    def markDirty(self):
        self.dirty = True

    def saveIfDirty(self):
        if self.dirty:
            self.save()
            self.dirty = False

PVEConfigCache = {}
def loadPVEConfig(file):
    global PVEConfigCache

    if file in PVEConfigCache:
        return PVEConfigCache[file]

    cfg = PVEConfig(file)
    PVEConfigCache[file] = cfg
    return cfg

def saveAllPVEConfigs():
    for key in PVEConfigCache:
        val = PVEConfigCache[key]
        val.saveIfDirty()
