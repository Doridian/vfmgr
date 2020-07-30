from config import CONFIG, SCRIPT_DIR, save as config_save
from sys import argv
from os import scandir, chdir
from iface import getVFConfigs, getVFStates, findFreeVF, findVFByVMIDAndVLAN, VF, DEFAULT_MAC
from pve import getVMIDList, saveAllPVEConfigs

cmd = argv[1]
iface = CONFIG['interface']

if cmd == 'show':
    iflen = 10

    vfConfigs = getVFConfigs(iface)
    vfStates = getVFStates(iface)

    vfStateMap = {}

    for vfState in vfStates:
        vfStateMap[vfState.idx] = vfState

    print('  '.ljust(iflen) + '                          CONFIG | CURRENT                | STATE')
    print('PF'.ljust(iflen) + '  VF VMID VLAN MAC               | VLAN MAC               | VLAN MAC')
    for vf in getVFConfigs(iface):
        vfState = vfStateMap[vf.idx]
        vlanStr = 'GOOD'
        if vfState.vlan != vf.vlan:
            macStr = 'BAD '
        macStr = 'GOOD'
        if vfState.mac != vf.mac:
            macStr = 'BAD '
        print(vf.tabular(iflen) + ' | ' + vfState.tabular(iflen, True) + ' | ' + vlanStr + ' ' + macStr)

elif cmd == 'add':
    vmid = int(argv[2], 10)
    vlan = int(argv[3], 10)

    if findVFByVMIDAndVLAN(iface, vmid, vlan):
        raise Exception('Cannot have two interfaces with same VLAN on VM')

    vf = findFreeVF(iface)
    if not vf:
        raise Exception('No free interfaces found on {iface}')

    vf.vmid = vmid
    vf.vlan = vlan

    vf.syncConfig()
    vf.applyOS()
    vf.applyVM(vmid)
    config_save()

    print(f'Added interface {vf.getPHYName()} with MAC {vf.mac}')
elif cmd == 'rm':
    vmid = int(argv[2], 10)
    vlan = None
    if len(argv) > 3:
        vlan = int(argv[3], 10)
    vf = findVFByVMIDAndVLAN(iface, vmid, vlan)
    vf.vmid = None
    vf.vlan = 0

    vf.syncConfig()
    vf.applyOS()
    vf.applyVM(vmid)
    config_save()

    print(f'Removed interface {vf.getPHYName()}')
elif cmd == 'mv':
    vmid = int(argv[2], 10)
    oldVlan = None
    newVlan = None
    if len(argv) > 4:
        oldVlan = int(argv[3], 10)
        newVlan = int(argv[4], 10)
    else:
        newVlan = int(argv[3], 10)

    vf = findVFByVMIDAndVLAN(iface, vmid, oldVlan)
    vf.vlan = newVlan

    vf.syncConfig()
    vf.applyOS()
    vf.applyVM(vmid)
    config_save()

    print(f'Moved interface {vf.getPHYName()} to VLAN {newVlan}')
elif cmd == 'apply':
    applyType = None
    if len(argv) > 2:
        applyType = argv[2].upper()

    doPVE = applyType == 'PVE' or not applyType
    doOS = applyType == 'OS' or not applyType

    vmidList = []

    if doPVE:
        vmidList = getVMIDList()

    for vf in getVFConfigs(None):
        if doOS:
            vf.applyOS()

        if doPVE:
            for vmid in vmidList:
                vf.applyVM(vmid)
    if doOS:
        print('Applied config to OS!')
    if doPVE:
        print('Applied config to PVE!')
elif cmd == 'fixmacs':
    for vf in getVFConfigs(None):
        vf.mac = vf.mac.lower()
        vf.syncConfig()
    config_save()
    print('Lowercased all MACs')
elif cmd == 'fixorphans':
    vmidList = getVMIDList()
    for vf in getVFConfigs(None):
        if vf.vmid == None or vf.vmid in vmidList:
            continue
        print(f'Orphan found: {vf.getPHYName()} points to VM {vf.vmid}')
else:
    print(f'Invalid command: {cmd}\n')
    f = open(f'{SCRIPT_DIR}/README', 'r')
    print(f.read())
    f.close()

saveAllPVEConfigs()
