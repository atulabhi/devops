import sys
import os
import time
import json
import logging
from time import ctime
from tsmUtils import listTSMWithIP_new
from vdbenchUtils import executeVdbenchFile
from haUtils import change_node_state, ping_machine
from volumeUtils import create_volume, delete_volume, getDiskAllocatedToISCSI, \
        mount_iscsi, listVolumeWithTSMId_new
from utils import check_mendatory_arguments, is_blocked, get_logger_footer, \
        assign_iniator_gp_to_LUN, discover_iscsi_lun, iscsi_login_logout, \
        get_iscsi_device, execute_mkfs, get_node_ip 
from cbrequest import get_url, configFile, sendrequest, resultCollection, \
        getControllerInfo, executeCmd, get_apikey, executeCmdNegative, getoutput

logging.basicConfig(format = '%(asctime)s %(message)s', filename = \
        'logs/automation_execution.log', filemode = 'a', level=logging.DEBUG)

logging.info('------------------------------ungracefull HA test case(iSCSI)'\
        'started------------------------------')
startTime = ctime()
EXECUTE_SYNTAX = 'python ungraceFullHAiSCSI.py conf.txt'
FOOTER_MSG = 'ungracefull HA test case(iSCSI) completed'
BLOCKED_MSG = 'Ungracefull HA test case(iSCSI) is blocked'

check_mendatory_arguments(sys.argv, 2, EXECUTE_SYNTAX, FOOTER_MSG, \
        BLOCKED_MSG, startTime)

conf = configFile(sys.argv)
DEVMAN_IP = conf['host']
USER = conf['username']
PASSWORD = conf['password']
VSM_IP = conf['ipVSM1']
APIKEY = get_apikey(conf)
NODE1_IP = None
PASSWD = 'test' # node password
#is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)
APIKEY = APIKEY[1]
STDURL = get_url(conf, APIKEY)
logging.debug('DEVMAN_IP: %s', DEVMAN_IP)
logging.debug('USER: %s', USER)
logging.debug('PASSWORD: %s', PASSWORD)
logging.debug('VSM_IP: %s', VSM_IP)
logging.debug('APIKEY: %s', APIKEY)
logging.debug('STDURL: %s', STDURL)

def getTsmInfo(tsms):
    if tsms[0] == 'PASSED':
        tsm = tsms[1]
        return tsm[0].get('name'), tsm[0].get('id'), tsm[0].get('datasetid'), \
                tsm[0].get('controllerid'), tsm[0].get('accountname'), \
                tsm[0].get('hapoolname')
    logging.error('ungracefull HA test case(iSCSI) blocked '\
            'due to %s', tsms[1])
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def controllerIP(tsms):
    if tsms[0] == 'PASSED':
        tsm = tsms[1]
        return tsm[0].get('controlleripaddress'), tsm[0].get('controllerName')
    logging.error('ungracefull HA test case(iSCSI) blocked '\
            'due to %s', tsms[1])
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def get_node2_ip(NODE1_IP, stdurl):
    querycommand = 'command=listController'
    logging.debug('executing listController...')
    listController_resp = sendrequest(stdurl, querycommand)
    data = json.loads(listController_resp.text)
    if 'errorcode' in str(data):
        errormsg = str(data['listControllerResponse'].get('errortext'))
        logging.error('ungracefull HA test case(iSCSI) blocked '\
                'due to %s', errormsg)
        is_blocked(startTime, FOOTER_MSG, errormsg)
    controllers = data['listControllerResponse']['controller']
    has_second_node = False
    has_first_node = False
    NODE2_IP = None
    for controller in controllers:
        if controller['ipAddress'] == NODE1_IP:
            node1_clustername = controller['clustername']
            has_first_node = True
            if has_second_node:
                if node2_clustername == node1_clustername:
                    return NODE2_IP
            continue
        node2_clustername = controller['clustername']
        NODE2_IP = controller['ipAddress']
        has_second_node = True
        if has_first_node:
            if node1_clustername == node2_clustername:
                return NODE2_IP
        if NODE2_IP is None:
            logging.error('ungracefull HA test case(iSCSI) blocked '\
                    'due to %s', 'There is no second Node')
            is_blocked(startTime, FOOTER_MSG, 'There is no second Node')
        return NODE2_IP


def verify_create_volume(result):
    if result[0] == 'PASSED':
        return
    logging.error('ungracefull HA test case(iSCSI) is blocked Volume '\
            'creation failed')
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_list_volumes(volumes):
    if volumes[0] == 'PASSED':
        logging.debug('volumes listed successfullly')
        return volumes[1]
    logging.error('Not able to list volumes due to %s', volumes[1])
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def get_vol_id(volumes, vol_name):
    volid = None
    voliqn = None
    accountid = None
    mntpoint = None
    for volume in volumes:
        if volume['name'] != vol_name:
            continue
        volid = volume.get('id')
        accountid = volume.get('accountid')
        voliqn = volume.get('iqnname')
        mntpoint = volume.get('mountpoint')
        break
    if volid is None or accountid is None or voliqn is None or mntpoint is None:
        logging.error('ungracefull HA test case(iSCSI) is blocked getting volid:'\
                '%s, accountid: %s, voliqn: %sand mntpoint: %s', \
                volid, accountid, voliqn, mntpoint)
        is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)
    return volid, voliqn, accountid, mntpoint

def verify_iqn(iqn):
    if iqn[0] == 'PASSED':
        return iqn[1]
    logging.debug('ungracefull HA test case(iSCSI) is blocked '\
            'getting iqn is None')
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_add_auth_gp(add_auth_group, auth_gp):
    if add_auth_group[0] == 'FAILED':
        logging.debug('ungracefull HA test case(iSCSI) is blocked Not able to '\
                'assign auth group %s to LUN', auth_gp)
        is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)
    return

def verify_iscsi_operation(result, vol_name, action):
    if result[0] == 'PASSED':
        logging.debug('%s successfully for iSCSI LUN %s', action, vol_name)
        return
    if 'already exists' in str(result[1]):
        logging.debug('iscsi LUN %s is already logged in, lets go ahead and' \
                'get the iscsi device name', vol_name)
        return
    logging.error('ungracefull HA test case(iSCSI) is blocked Not able to %s '\
            '%s, Error: %s', action, vol_name, str(result[1]))
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_iscsi_device(iscsi_device, iqn, VSM_IP):
    if iscsi_device[0] == 'PASSED':
        device = iscsi_device[1]
        return device
    logging.debug('executing iscsi logout, since not able to get iscsi device')
    result = iscsi_login_logout(iqn, VSM_IP, 'logout')
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_get_node_ip(result):
    if result[0] == 'PASSED':
        return result[1]
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_getDiskAllocatedToISCSI(result, mountpoint):
    if result[0] == 'PASSED' and mountpoint in str(result[1]):
        logging.debug('iscsi logged device... %s', result[1][mountpoint])
        return result[1][mountpoint]
    logging.error('Not able to get iscsi legged device')
    exit()

def verify_execute_mkfs(result):
    if result[0] == 'PASSED':
        return
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_mount(mount_result):
    if mount_result[0] == 'PASSED':
        return
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_pool_import(poolName, NODE2_IP, PASSWD):
    
    logging.debug('pool import at peer Node would take some time, '\
            'sleeping for 25 seconds')
    time.sleep(25)

    logging.debug('executing zpool list at Node:%s', NODE2_IP)
    getControllerInfo(NODE2_IP, PASSWD, 'zpool list', 'listpool.txt')
    import_result = executeCmd('cat listpool.txt | grep %s' %(poolName))
    if import_result[0] == 'PASSED':
        logging.debug('pool %s imported successfully at peer Node:%s', \
                poolName, NODE2_IP)
        return

    logging.debug('pool is not imported till 25 seconds after reboot the Node')
    logging.debug('sleeping for another 10 seconds')
    time.sleep(10)
    
    logging.debug('executing zpool list at Node:%s', NODE2_IP)
    getControllerInfo(NODE2_IP, PASSWD, 'zpool list', 'listpool.txt')
    import_result = executeCmd('cat listpool.txt | grep %s' %(poolName))
    if import_result[0] == 'PASSED':
        logging.debug('pool %s imported successfully at peer Node:%s', \
                poolName, NODE2_IP)
        return
    
    logging.debug('pool is not imported till 35 seconds after reboot the Node')
    logging.debug('sleeping for another 10 seconds')
    time.sleep(10)

    logging.debug('executing zpool list at Node:%s', NODE2_IP)
    getControllerInfo(NODE2_IP, PASSWD, 'zpool list', 'listpool.txt')
    import_result = executeCmd('cat listpool.txt | grep %s' %(poolName))
    if import_result[0] == 'PASSED':
        logging.debug('pool %s imported successfully at peer Node:%s', \
                poolName, NODE2_IP)
        return

    logging.error('pool %s import failed at peer Node:%s', poolName, NODE2_IP)
    is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_IOPS(NODE1_IP, PASSWD, iops_datapath):
    cmd = 'reng stats access dataset %s qos | head -n 4 ; sleep 2 ;\
            echo "-----------------"; reng stats access dataset %s qos |\
            head -n 4' %(iops_datapath, iops_datapath)
    logging.debug('executing the command %s in controller', str(cmd))
    iops_res = getControllerInfo(NODE1_IP, PASSWD, cmd, 'beforeHAIO1.txt')
    print iops_res
    logging.debug('iops result is %s', (iops_res))
    logging.debug('sleeping for 3 seconds before fatching new IOPS value...')
    time.sleep(3)
    logging.debug('executing the command %s in controller', str(cmd))
    iops_res = getControllerInfo(NODE1_IP, PASSWD, cmd, 'beforeHAIO2.txt')
    print iops_res
    logging.debug('iops result is %s', (iops_res))
    io_output = executeCmdNegative('diff beforeHAIO1.txt beforeHAIO2.txt')
    if io_output[0] == 'FAILED':
        msg = 'IOPS are not running, please make sure to run IOPS properly'
        logging.debug('Compared result: %s, Error: %s', io_output[0], msg)
        logging.debug('IOPS Error: Not going to reset the Node...')
        is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)
    elif io_output[0] == 'PASSED':
        msg =  "Iops are  running fine"
        logging.debug('Compared result: %s', msg)
        print msg
        return
    else:
        print "problem in comparing files"
        logging.error('problem in comparing files')
        is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

def verify_IOPS_afterHA(NODE2_IP, PASSWD, iops_datapath):
    endTime = ctime()
    cmd = 'reng stats access dataset %s qos | head -n 4 ; sleep 2 ;\
            echo "-----------------"; reng stats access dataset %s qos |\
            head -n 4' %(iops_datapath, iops_datapath)
    logging.debug('executing the command %s in controller', str(cmd))
    iops_res = getControllerInfo(NODE2_IP, PASSWD, cmd, 'afterHAIO1.txt')
    print iops_res
    logging.debug('iops result is %s', (iops_res))
    logging.debug('sleeping for 3 seconds before fatching new IOPS value...')
    time.sleep(3)
    logging.debug('executing the command %s in controller', str(cmd))
    iops_res = getControllerInfo(NODE2_IP, PASSWD, cmd, 'afterHAIO2.txt')
    print iops_res
    logging.debug('iops result is %s', (iops_res))
    io_output = executeCmdNegative('diff afterHAIO1.txt afterHAIO2.txt')
    if io_output[0] == 'FAILED':
        msg = 'IOPS are not running after HA failover...'
        logging.debug('Compared result: %s, Error: %s', io_output[0], msg)
        logging.debug('IOPS Error: ungracefull HA test case(iSCSI) failed...')
        resultCollection('Ungracefull HA test case(iSCSI) failed', \
                ['FAILED', ''], startTime, endTime)
    elif io_output[0] == 'PASSED':
        msg =  "IOPS are  running fine after ungracefull HA"
        logging.debug('Compared result: %s', msg)
        resultCollection('Ungracefull HA test case(iSCSI) passed', \
                ['PASSED', ''], startTime, endTime)
        print msg
    else:
        print "problem in comparing files"
        logging.error('problem in comparing files')
        is_blocked(startTime, FOOTER_MSG, BLOCKED_MSG)

logging.info('listing TSMs with IP...')
tsms = listTSMWithIP_new(STDURL, VSM_IP)
#logging.debug('tsms... %s', str(tsms))
logging.info('getting tsm_name, tsm_id, and dataset_id...')
tsm_name, tsm_id, dataset_id, controllerid, accName, poolName = getTsmInfo(tsms)
logging.debug('tsm_name:%s, tsm_id:%s, dataset_id:%s, controllerid:%s, '\
        'accName:%s, poolName:%s', tsm_name, tsm_id, dataset_id, \
        controllerid, accName, poolName)

result = get_node_ip(STDURL, controllerid)
NODE1_IP = verify_get_node_ip(result)
NODE2_IP = get_node2_ip(NODE1_IP, STDURL)
volumeDict = {'name': 'ungrceHAiSCSI1', 'tsmid': tsm_id, 'datasetid': \
        dataset_id, 'protocoltype': 'ISCSI', 'iops': 500}
result = create_volume(volumeDict, STDURL)
verify_create_volume(result)
logging.info('listing volume...')
volumes = listVolumeWithTSMId_new(STDURL, tsm_id)
volumes = verify_list_volumes(volumes)
vol_id, vol_iqn, account_id, mnt_point = get_vol_id(volumes, volumeDict['name'])
logging.debug('volume_id: %s, aacount_id: %s, mountpoint: %s and vol_iqn: %s', \
        vol_id, account_id, mnt_point, vol_iqn)

add_auth_group = assign_iniator_gp_to_LUN(STDURL, vol_id, account_id, 'ALL')
verify_add_auth_gp(add_auth_group, 'ALL')

logging.debug('getting iqn for volume %s', volumeDict['name'])
iqn = discover_iscsi_lun(VSM_IP, vol_iqn)
iqn = verify_iqn(iqn)
logging.debug('iqn for discovered iSCSI LUN... %s', iqn)

login_result = iscsi_login_logout(iqn, VSM_IP, 'login')
verify_iscsi_operation(login_result, volumeDict['name'], 'login')
time.sleep(2)
result = getDiskAllocatedToISCSI(VSM_IP, mnt_point)
iscsi_device = verify_getDiskAllocatedToISCSI(result, mnt_point)
result = execute_mkfs(iscsi_device, 'ext3')
verify_execute_mkfs(result)
mount_result = mount_iscsi(iscsi_device, volumeDict['name'])
verify_mount(mount_result)
#mount_dir = 'mount/%s' %(volumeDict['name'])
mount_dir = {'name': volumeDict['name'], 'mountPoint': volumeDict['name']}
logging.info('...executing vdbench....')
executeVdbenchFile(mount_dir, 'filesystem_iscsi')
time.sleep(20)
logging.info('verifying the IOPS before Node goes to reset...')
iops_datapath = poolName+'/'+accName+tsm_name+'/'+volumeDict['name']
verify_IOPS(NODE1_IP, PASSWD, iops_datapath)
logging.debug('going to move node to reset...')
getControllerInfo(NODE1_IP, PASSWD, 'reboot', 'reboot.txt')

logging.debug('verifying pool import at peer Node: %s', NODE2_IP)
verify_pool_import(poolName, NODE2_IP, PASSWD)
logging.debug('before verifying IOPS after reset the Node, sleeping for 10secs')
time.sleep(10)
logging.debug('verifying IOPS at peer Node IP: %s', NODE2_IP)
verify_IOPS_afterHA(NODE2_IP, PASSWD, iops_datapath)

#Wait till Node come up and move it to available state
logging.debug('Waiting for 3 minutes to come up the Node:%s, It may take 5 to '\
        '15 minutes', NODE1_IP)
time.sleep(180)
node_online = True
ping_result = ping_machine(NODE1_IP)
count = 1
while ping_result[0] == 'FAILED':
    if count == 4:
        logging.error('Node %s did not come up after 15 minutes, So can not '\
                'make it available ', NODE1_IP)
        node_online = False
        break
    logging.debug('Still Node %s did not come UP, sleeping for 3 more minutes',\
            NODE1_IP)
    time.sleep(180)
    count = count + 1
    ping_result = ping_machine(NODE1_IP)

logging.debug('ungracefull HA test case(iSCSI) completed, executing '\
        'umount and logout iSCSI LUN')
umount_result = executeCmd('umount /dev/%s1' %(iscsi_device))
if umount_result[0] == 'FAILED':
    logging.error('Not able to umount /dev/%s1, still go ahead and logout '\
            'the iSCSI LUN, since test case is complete', iscsi_device)
else:
    logging.debug('LUN /dev/%s1 umounted successfully', iscsi_device)
logout_result = iscsi_login_logout(iqn, VSM_IP, 'logout')
if logout_result[0] == 'FAILED':
    logging.error('Not able to logged out iSCSI LUN, still go ahead and '\
            'set auth group to None, since test case is complete')
else:
    logging.debug('iSCSI LUN logged out successfully')

remove_configuration = False
if node_online:
    #There might be few chances to Node come up, and suddenly we move it...
    #to available state, so sleep for 5 seconds
    time.sleep(5)
    available_state = change_node_state(STDURL, NODE1_IP, 'available')
    if available_state == 'FAILED':
        logging.debug('Not able to move Node to available state, Will not be '\
                'able to remove configuration')
    else:
        logging.debug('Node with IP: %s is in available state, removing '\
                'configuration', NODE1_IP)
        remove_configuration = True
else:
    logging.debug('Node did not come up can not remove configuration, please '\
            'check it manually...')

if remove_configuration:
    logging.debug('ungracefull HA test case(iSCSI) completed, removing '\
            'configuration')
    add_auth_grup = assign_iniator_gp_to_LUN(STDURL, vol_id, account_id, 'None')
    if add_auth_grup[0] == 'FAILED':
        logging.error('Not able to set auth group to None, do not delete volume')
        get_logger_footer('ungracefull HA test case(iSCSI) completed')
    else:
        logging.debug('Go and delete the volume')
        delete_volume(vol_id, STDURL)
        get_logger_footer('ungracefull HA test case(iSCSI) completed')
