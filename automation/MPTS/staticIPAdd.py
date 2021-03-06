import json
import sys
from time import ctime
from cbrequest import sendrequest, filesave, timetrack, queryAsyncJobResult, configFile, resultCollection, getControllerInfo

config = configFile(sys.argv);
stdurl = 'https://%s/client/api?apikey=%s&response=%s&' %(config['host'], config['apikey'], config['response'])

if len(sys.argv)< 4:
    print "Argument is not correct.. Correct way as below"
    print "python staticIPAdd.py config.txt NodeIP NodePassword"
    exit()
IP=sys.argv[2]
Password=sys.argv[3]



for x in range(1, int(config['Number_of_StaticIPs'])+1):
    startTime = ctime()
    ###TO list the ControllerID
    controller_id = ""
    querycommand = 'command=listController'
    resp_listController = sendrequest(stdurl, querycommand)
    filesave("logs/listController.txt", "w",resp_listController)
    data = json.loads(resp_listController.text)
    controllers = data['listControllerResponse']['controller']
    #controller_list = data['listControllerResponse']['controller']
    #print controllers
    for controller in controllers:
        if controller['name'] == "%s" %(config['staticIPControllerName%d' %(x)]):
            #controller_id = data['listControllerResponse']['controller'][0]['id']
            controller_id = controller['id']
            #print "ControllerID = %s" %(controller_id)
            nics = controller['nics']
            #print nics
            for nic in nics:
                if nic['name'] == config['staticIPInterface%d' %x]:
                    nic_id = nic['nicid']
                    #print "Nic id %s" %(nic_id)
                    break



    querycommand = 'command=assignStaticIP&controllerid=%s&ipaddress=%s&subnet=%s&gateway=%s&id=%s' %(controller_id, config['staticIP%d' %(x)], config['staticIPSubnet%d' %(x)], config['staticIPGateway%d' %(x)], nic_id)
    resp_assignStaticIP = sendrequest(stdurl, querycommand)
    data=json.loads(resp_assignStaticIP.text)
    #staticIPResponse = data['nicResponse']

    filesave("logs/assignStaticIP.txt","w", resp_assignStaticIP)

    if not "errortext" in str(data):
        print "Static IP added successfully"
        endTime = ctime()
        resultCollection("Static IP Addition %s Verification from Devman" %(config['staticIPInterface%d' %(x)]), ["PASSED", ""],startTime,endTime) 
    else:
        print "Static IP addition Failed "
        errorstatus= str(data['nicResponse']['errortext'])
        endTime = ctime()
        resultCollection("Static IP Addition %s Verification from Devman" %(config['staticIPInterface%d' %(x)]), ["FAILED", errorstatus],startTime,endTime) 

    routput = getControllerInfo(IP, Password, "ifconfig %s | grep inet" %(config['staticIPInterface%d' %(x)]), "logs/test");
    #print routput 

    if (("%s" %(config['staticIP%d' %(x)]) in str(routput)) and ("%s" %(config['staticIPGateway%d' %(x)]) in str(routput))):
        endTime = ctime()
        resultCollection("Static IP Addition %s Verification from Node" %(config['staticIPInterface%d' %(x)]), ["PASSED", ""],startTime,endTime) 
    else:
        endTime = ctime()
        resultCollection("Static IP Addition %s Verification from Node" %(config['staticIPInterface%d' %(x)]), ["FAILED", str(routput)],startTime,endTime) 







