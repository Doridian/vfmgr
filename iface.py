from config import CONFIG, LXC_DIR, QEMU_DIR
from subprocess import call, run, PIPE
from os import readlink
from pve import loadPVEConfig
from random import randint

DEFAULT_MAC = '00:00:00:00:00:00'
DEFAULT_VLAN = 4095

class VF:
    def __init__(self, iface, cfg=None):
        self.iface = iface
        self.driver = CONFIG['drivers'][self.iface]

        if cfg == None:
            self.idx = None
            self.mac = None
            self.vlan = None
            self.vmid = None
            self.spoofchk = None
            self.linkstate = None
            self.macvtap = False
            return
            
        self.idx = cfg['idx']

        if 'mac' in cfg:
            self.mac = cfg['mac']
        else:
            self.mac = None
            self.randomMAC()

        if 'vlan' in cfg:
            self.vlan = cfg['vlan']
        else:
            self.vlan = DEFAULT_VLAN

        if 'vmid' in cfg:
            self.vmid = cfg['vmid']
        else:
            self.vmid = None

        if 'spoofchk' in cfg:
            self.spoofchk = cfg['spoofchk']
        else:
            self.spoofchk = 'on'

        if 'linkstate' in cfg:
            self.linkstate = cfg['linkstate']
        else:
            self.linkstate = 'enable'

        if 'macvtap' in cfg:
            self.macvtap = cfg['macvtap']
        else:
            self.macvtap = False

        self.cfg = cfg
        self.syncConfig()
    
    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f'PF {self.iface}; VF {self.idx}; MAC {self.mac}; VMID {self.vmid}; VLAN {self.vlan}'

    def tabular(self, iflen, onlyState=False):
        vlanStr = '    '
        if self.vlan != DEFAULT_VLAN:
            vlanStr = '% 4d' % self.vlan

        vfStr = '% 3d' % self.idx

        vmidStr = '    '
        if self.vmid != None:
            vmidStr = '% 4d' % self.vmid
        
        if onlyState:
            return f'{vlanStr} {self.mac}'

        return f'{self.iface.ljust(iflen)} {vfStr} {vmidStr} {vlanStr} {self.mac}'

    def randomMAC(self):
        if self.mac != None and self.mac != DEFAULT_MAC:
            return

        macValid = False
        while not macValid:
            self.mac = ('52:54:00:%02x:%02x:%02x' % (randint(0, 255), randint(0, 255), randint(0, 255))).lower()
            macValid = True
            for vf in getVFConfigs(None):
                if vf.mac.lower() == self.mac:
                    macValid = False
                    break

    def syncConfig(self):
        self.cfg['mac'] = self.mac
        if self.vmid == None:
            self.cfg.pop('vmid', None)
        else:
            self.cfg['vmid'] = self.vmid

        if self.vlan == DEFAULT_VLAN:
            self.cfg.pop('vlan', None)
        else:
            self.cfg['vlan'] = self.vlan

    def valid(self):
        return self.idx != None and self.iface != None and self.vlan != None and self.mac != None

    def applyOS(self):
        if not self.valid():
            raise Exception("Invalid iface config!")

        phyName = self.getPHYName()

        res = call(['ip', 'link', 'set', phyName, 'down'])
        if res != 0 and (self.vmid == None or self.macvtap):
            self.rebindDriver()
            call(['ip', 'link', 'set', phyName, 'down'])

        res = call(['ip', 'link', 'set', self.iface, 'vf', str(self.idx), 'vlan', str(self.vlan), 'mac', self.mac, 'spoofchk', self.spoofchk])
        if res != 0:
            raise Exception("VF config failed")
        call(['ip', 'link', 'set', self.iface, 'vf', str(self.idx), 'state', self.linkstate])
        call(['ip', 'link', 'set', phyName, 'address', self.mac])

        if self.macvtap and self.vmid != None:
            call(['ip', 'link', 'add', f'vmlan{self.vmid}', 'link', phyName, 'type', 'macvtap', 'mode', 'passthru'])
            call(['ip', 'link', 'set', 'dev', f'vmlan{self.vmid}', 'up'])
            call(['ip', 'link', 'set', 'dev', phyName, 'up'])

    # Returns (True, index) OR (False, nextFreeIndex)
    def _findSelfInLXC(self, lxcData):
        phyName = self.getPHYName()

        iN = 0
        while f'lxc.net.{iN}.type' in lxcData.cfg:
            i = iN
            iN += 1

            if lxcData.cfg[f'lxc.net.{i}.type'] != 'phys':
                continue
            if lxcData.cfg[f'lxc.net.{i}.link'] != phyName:
                continue

            return (True, i)

        return (False, iN)

    # Returns (True, index) OR (False, nextFreeIndex)
    def _findSelfInQEMU(self, qemuData):
        pcieAddr = self.getPCIeAddr()

        iN = 0
        while f'hostpci{iN}' in qemuData.cfg:
            i = iN
            iN += 1

            pciConf = qemuData.cfg[f'hostpci{i}']
            if pciConf.startswith('0000:'):
                pciConf = pciConf[5:]

            if pciConf.startswith(pcieAddr):
                return (True, i)

        return (False, iN)

    def applyVM(self, vmid=None, dosave=True):
        if not self.valid():
            raise Exception("Invalid iface config!")

        if not vmid:
            vmid = self.vmid
            if not vmid:
                return

        shouldExist = vmid == self.vmid

        if self.macvtap:
            shouldExist = False

        lxcConf = f'{LXC_DIR}{vmid}.conf'
        qemuConf = f'{QEMU_DIR}{vmid}.conf'

        try:
            lxcData = loadPVEConfig(lxcConf)
            lxcName = self.getLXCName()
            phyName = self.getPHYName()

            hadChanges = False
            found, idx = self._findSelfInLXC(lxcData)

            if shouldExist:
                if not found:
                    lxcData.cfg[f'lxc.net.{idx}.type'] = 'phys'
                    lxcData.cfg[f'lxc.net.{idx}.link'] = phyName
                    lxcData.cfg[f'lxc.net.{idx}.name'] = lxcName
                    hadChanges = True
                elif lxcData.cfg[f'lxc.net.{idx}.name'] != lxcName:
                    lxcData.cfg[f'lxc.net.{idx}.name'] = lxcName
                    hadChanges = True
            elif found:
                hadChanges = True
                while True:
                    lxcData.cfg.pop(f'lxc.net.{idx}.type', None)
                    lxcData.cfg.pop(f'lxc.net.{idx}.link', None)
                    lxcData.cfg.pop(f'lxc.net.{idx}.name', None)
                    nextIdx = idx + 1
                    if not f'lxc.net.{nextIdx}.type' in lxcData.cfg:
                        break
                    lxcData.cfg[f'lxc.net.{idx}.type'] = lxcData.cfg[f'lxc.net.{nextIdx}.type']
                    lxcData.cfg[f'lxc.net.{idx}.name'] = lxcData.cfg[f'lxc.net.{nextIdx}.name']
                    if f'lxc.net.{nextIdx}.link' in lxcData.cfg:
                        lxcData.cfg[f'lxc.net.{idx}.link'] = lxcData.cfg[f'lxc.net.{nextIdx}.link']
                    idx = nextIdx

            if hadChanges:
                print(f'Found changes for {self.getPHYName()} in LXC {vmid}!')
                lxcData.markDirty()
        except FileNotFoundError:
            pass

        try:
            qemuData = loadPVEConfig(qemuConf)
            pcieAddr = self.getPCIeAddr()

            hadChanges = False
            found, idx = self._findSelfInQEMU(qemuData)

            pciLine = f'{pcieAddr},pcie=1'

            if shouldExist:
                if not found or qemuData.cfg[f'hostpci{idx}'] != pciLine:
                    qemuData.cfg[f'hostpci{idx}'] = pciLine
                    hadChanges = True
            elif found:
                hadChanges = True
                while True:
                    qemuData.cfg.pop(f'hostpci{idx}', None)
                    nextIdx = idx + 1
                    if not f'hostpci{nextIdx}' in qemuData.cfg:
                        break
                    qemuData.cfg[f'hostpci{idx}'] = qemuData.cfg[f'hostpci{nextIdx}']
                    idx = nextIdx

            if hadChanges:
                print(f'Found changes for {self.getPHYName()} in QEMU {vmid}!')
                qemuData.markDirty()
        except FileNotFoundError:
            pass

    def getPHYName(self):
        return f'{self.iface}v{self.idx}'

    def getLXCName(self):
        return f'eth{self.vlan}'

    def getDevicePath(self):
        return f'/sys/class/net/{self.iface}/device/virtfn{self.idx}'

    def getPCIeAddr(self, strip=True):
        pciDevPath = readlink(self.getDevicePath())
        pcieAddr = pciDevPath.split('/')[1]
        if strip and pcieAddr.startswith('0000:'):
            return pcieAddr[5:]
        return pcieAddr

    def rebindDriver(self):
        pcieAddr = self.getPCIeAddr(False)

        print(f'Rebinding device {pcieAddr} [{self.getPHYName()}] to {self.driver}')

        # Unbind whatever old driver we have
        try:
            fh = open(f'{self.getDevicePath()}/driver/unbind', 'w')
            fh.write(pcieAddr)
            fh.close()
        except FileNotFoundError:
            pass

        # Bind correct driver
        fh = open(f'/sys/bus/pci/drivers/{self.driver}/bind', 'w')
        fh.write(pcieAddr)
        fh.close()

def getVFStates(iface):
    res = run(['ip', 'link', 'show', 'dev', iface], stdout=PIPE)
    out = res.stdout.decode('ascii').split('\n')
    vfs = []
    for line in out:
        line = line.strip()
        if not line.startswith('vf '):
            continue
        linespl = line.replace(',', ' ').split(' ')
        vfconf = VF(iface)
        for i in range(0, len(linespl) - 1):
            spl = linespl[i]
            splo = linespl[i + 1]
            if spl == 'vf':
                vfconf.idx = int(splo, 10)
            elif spl == 'MAC':
                if splo != DEFAULT_MAC:
                    vfconf.mac = splo
            elif spl == 'vlan':
                vfconf.vlan = int(splo, 10)
            elif spl == 'spoofchk':
                vfconf.spoofchk = splo
            elif spl == 'link-state':
                vfconf.linkstate = splo
        vfs += [vfconf]
    return vfs

def getMaxVFIdx(iface):
    vfs = getVFStates(iface)
    maxIdx = 0
    for vf in vfs:
        if vf.idx > maxIdx:
            maxIdx = vf.idx
    return maxIdx

# Once multi-iface hits: None will be "all interfaces"
def getVFConfigs(iface):
    vfs = []
    for vfcfg in CONFIG['vfs']:
        vf = VF(CONFIG['interface'], vfcfg)
        vfs += [vf]
    return vfs

def findFreeVF(iface):
    usedVFs = {}

    for vf in getVFConfigs(iface):
        usedVFs[vf.idx] = vf

    for i in range(0, getMaxVFIdx(iface) + 1):
        if i in usedVFs:
            vf = usedVFs[i]
            if vf.vmid != None:
                continue
            return vf
        else:
            cfg = {}
            cfg['idx'] = i
            CONFIG['vfs'] += [cfg]
            return VF(iface, cfg)

    return None

def findVFByVMIDAndVLAN(iface, vmid, vlan=None):
    for vf in getVFConfigs(iface):
        if vf.vmid != vmid:
            continue
        if vlan != None and vf.vlan != vlan:
            continue
        return vf
