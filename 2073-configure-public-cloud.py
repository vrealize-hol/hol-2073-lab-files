####### I M P O R T A N T #######
## If you are deploying this vPod dircetly in OneCloud and not through the Hands On Lab portal,
## you must uncomment the following lines and supply your own set of AWS and Azure keys
#################################
# awsid = "put your AWS access key here"
# awssec = "put your AWS secret hey here"
# azsub = "put your azure subscription id here"
# azten = "put your azure tenant id here"
# azappkey = "put your azure application key here"
# azappid = "put your azure application id here"

import json
import requests
import time
import os
import traceback
import boto3
from boto3.dynamodb.conditions import Key, Attr
from random import seed, randint
import datetime
import calendar
from time import strftime
import subprocess
import re
import sys
import urllib3
urllib3.disable_warnings()


d_id = os.getenv('D_ID')
d_sec = os.getenv('D_SEC')
d_reg = os.getenv('D_REG')
vra_fqdn = "vr-automation.corp.local"
api_url_base = "https://" + vra_fqdn + "/"

# set internet proxy for for communication out of the vPod
proxies = {
    "http": "http://192.168.110.1:3128",
    "https": "https://192.168.110.1:3128"
}

slack_api_key = os.getenv('SLACK_KEY')

def get_vlp_urn():
    # determine current pod's URN (unique ID) using Main Console guestinfo
    # this uses a VLP-set property named "vlp_vapp_urn" and will only work for a pod deployed by VLP

    tools_location = 'C:\\Program Files\\VMware\\VMware Tools\\vmtoolsd.exe'
    command = '--cmd "info-get guestinfo.ovfenv"'
    full_command = tools_location + " " + command

    if os.path.isfile(tools_location):
        response = subprocess.run(full_command, stdout=subprocess.PIPE)
        byte_response = response.stdout
        txt_response = byte_response.decode("utf-8")

        try:
            urn = re.search('urn:vcloud:vapp:(.+?)"/>', txt_response).group(1)
        except:
            return('No urn parameter found')

        if len(urn) > 0:
            return urn
        else: 
            return('No urn value found')
        
    else:
        return('Error: VMware tools not found')


def get_available_pod():
    # this function checks the dynamoDB to see if there are any available AWS and Azure key sets to configure the cloud accounts

    dynamodb = boto3.resource('dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    response = table.scan(
        FilterExpression=Attr('reserved').eq(0),
        ProjectionExpression="pod, in_use"
    )
    pods = response['Items']
    # the number of pods not reserved
    num_not_reserved = len(pods)
    available_pods = 0  # set counter to zero
    pod_array = []
    for i in pods:
        if i['in_use'] == 0:  # pod is available
            available_pods += 1  # increment counter
            pod_array.append(i['pod'])

    if available_pods == 0:  # all credentials are assigned
        # get the oldest credentials and re-use those
        response = table.scan(
            FilterExpression=Attr('check_out_epoch').gt(0),
            ProjectionExpression="pod, check_out_epoch"
        )
        pods = response['Items']
        oldest = pods[0]['check_out_epoch']
        pod = pods[0]['pod']
        for i in pods:
            if i['check_out_epoch'] < oldest:
                pod = i['pod']
                oldest = i['check_out_epoch']
    else:
        # get random pod from those available
        dt = datetime.datetime.microsecond
        seed(dt)
        rand_int = randint(0, available_pods-1)
        pod = pod_array[rand_int]
    return(pod, num_not_reserved, available_pods)

def get_creds(cred_set,vlp_urn_id):

    dynamodb = boto3.resource('dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    a = time.gmtime()   #gmt in structured format
    epoch_time = calendar.timegm(a)     #convert to epoc
    human_time = strftime("%m-%d-%Y %H:%M", a)

    #get the key set
    response = table.get_item(
        Key={
            'pod': cred_set
        }
    )
    results = response['Item']

    #write some items
    response = table.update_item(
        Key={
            'pod': cred_set
        },
        UpdateExpression="set in_use = :inuse, vlp_urn=:vlp, check_out_epoch=:out, check_out_human=:hout",
        ExpressionAttributeValues={
            ':inuse': 1,
            ':vlp': vlp_urn_id,
            ':out': epoch_time,
            ':hout': human_time
        },
        ReturnValues="UPDATED_NEW"
    )

    return(results)

def send_slack_notification(payload):
    slack_url = 'https://hooks.slack.com/services/'
    post_url = slack_url + slack_api_key
    requests.post(url=post_url, proxies=proxies, json=payload)
    return()


def extract_values(obj, key):
    """Pull all values of specified key from nested JSON."""
    arr = []
    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr
    results = extract(obj, arr, key)
    return results

def get_token():
    api_url = '{0}csp/gateway/am/api/login?access_token'.format(api_url_base)
    data =  {
              "username":"admin",
              "password": "VMware1!"
            }
    response = requests.post(api_url, headers=headers, data=json.dumps(data), verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        key = json_data['access_token']
        return key
    else:
        return('not ready')

def vra_ready():  # this is a proxy to test whether vRA is ready or not since the deployments service is one of the last to come up
    api_url = '{0}deployment/api/deployments'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        ready = True
    else:
        ready = False
    return(ready)

def create_aws_ca():
    api_url = '{0}iaas/api/cloud-accounts-aws'.format(api_url_base)
    data =  {
                "description": "AWS Cloud Account",
                "accessKeyId": awsid,
                "secretAccessKey": awssec,
                "cloudAccountProperties": {

                },
                "regionIds": [
                    "us-west-1",
                    "us-west-2"
                ],
                "tags": [
                            {
                                "key": "hol.cloud.account.source", 
                                "value": "aws"
                            },
                            {
                                "key" : "hol.cloud.account.owner", 
                                "value" : "hol_project"
                            }
                        ],
                "createDefaultZones" : "true",
                "name": "AWS Cloud Account"
            }
    response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
    if response.status_code == 201:
        print('- Successfully Created AWS Cloud Account')
    else:
        print('- Failed to Create the AWS Cloud Account')
        return None

def create_azure_ca():
    api_url = '{0}iaas/api/cloud-accounts-azure'.format(api_url_base)
    data =  {
              "name": "Azure Cloud Account",
              "description": "Azure Cloud Account",
              "subscriptionId": azsub,
              "tenantId": azten,
              "clientApplicationId": azappid,
              "clientApplicationSecretKey": azappkey,
              "regionIds": [
                  "westus"
               ],
               "tags": [
                            {
                                "key": "hol.cloud.account.source", 
                                "value": "azure"
                            },
                            {
                                "key" : "hol.cloud.account.owner", 
                                "value" : "hol_project"
                            }
                        ],
              "createDefaultZones": "true"
            }
    response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
    if response.status_code == 201:
        print('- Successfully Created Azure Cloud Account')
    else:
        print('- Failed to create the Azure Cloud Account')
        return None

def get_czids():
    api_url = '{0}iaas/api/zones'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        cz_id = extract_values(json_data,'id')
        return cz_id
    else:
        print('- Failed to get the cloud zone IDs')
        return None

def get_right_czid_vsphere(czid):
    api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,czid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        cz_name = extract_values(json_data,'name')
        for x in cz_name:
            if x == 'vRA-Managed vSphere Compute':
                return czid
    else:
        print('- Failed to get the right vSphere cloud zone ID')
        return None

def get_right_czid_aws_west1(czid):
    api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,czid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        cz_name = extract_values(json_data,'name')
        for x in cz_name:
            if x == 'AWS Cloud Account / us-west-1':
                return czid
    else:
        print('- Failed to get the right AWS west 1 cloud zone ID')
        return None

def get_right_czid_aws_west2(czid):
    api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,czid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        cz_name = extract_values(json_data,'name')
        for x in cz_name:
            if x == 'AWS Cloud Account / us-west-2':
                return czid
    else:
        print('- Failed to get the right AWS west 2 cloud zone ID')
        return None

def get_right_czid_azure(czid):
    api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,czid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        cz_name = extract_values(json_data,'name')
        for x in cz_name:
            if x == 'Azure Cloud Account / westus':
                return czid
    else:
        print('- Failed to get Azure cloud zone ID')
        return None

def get_czid_aws(czid):
    for x in czid:
        api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,x)
        response = requests.get(api_url, headers=headers1, verify=False)
        if response.status_code == 200:
            json_data = json.loads(response.content.decode('utf-8'))
            cz_name = extract_values(json_data,'name')
            cz_name = cz_name[0]
            if cz_name == 'AWS-West-1 / us-west-1':
                return x
        else:
            print('- Failed to get the AWS 1 cloud zone ID')
            return None

def get_projids():
    api_url = '{0}iaas/api/projects'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        proj_id = extract_values(json_data,'id')
        return proj_id
    else:
        print('- Failed to get the project IDs')
        return None

def get_right_projid(projid):
    api_url = '{0}iaas/api/projects/{1}'.format(api_url_base,projid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        proj_name = extract_values(json_data,'name')
        for x in proj_name:
            if x == 'HOL Project':
                return projid
    else:
        print('- Failed to get the right project ID')
        return None

def get_right_projid_rp(projid):
    api_url = '{0}iaas/api/projects/{1}'.format(api_url_base,projid)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        proj_name = extract_values(json_data,'name')
        for x in proj_name:
            if x == 'Rainpole Project':
                return projid
    else:
        print('- Failed to get the right project ID')
        return None

def update_project(proj_Ids,vsphere,aws1,aws2,azure):
    if proj_Ids is not None:
        for x in proj_Ids:
            project_id = get_right_projid(x)
            if project_id is not None:
                api_url = '{0}iaas/api/projects/{1}'.format(api_url_base,project_id)
                data =  {
                            "name": "HOL Project",
                        	"zoneAssignmentConfigurations": [
                                        {
                                            "zoneId": vsphere,
                                            "maxNumberInstances": 20,
                                            "priority": 1
                                        },
                                        {
                                            "zoneId": aws1,
                                            "maxNumberInstances": 10,
                                            "priority": 1
                                        },
                                        {
                                            "zoneId": aws2,
                                            "maxNumberInstances": 10,
                                            "priority": 1
                                        },
                                        {
                                            "zoneId": azure,
                                            "maxNumberInstances": 10,
                                            "priority": 1
                                        }
                                    ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully added cloud zones to HOL Project')
                else:
                    print('- Failed to add cloud zones to HOL Project')
                    return None

def update_project_rp(proj_Ids,vsphere,aws1,aws2,azure):
    if proj_Ids is not None:
        for x in proj_Ids:
            project_id = get_right_projid_rp(x)
            if project_id is not None:
                api_url = '{0}iaas/api/projects/{1}'.format(api_url_base,project_id)
                data =  {
                            "name": "Rainpole Project",
                        	"zoneAssignmentConfigurations": [
                                        {
                                            "zoneId": vsphere,
                                            "maxNumberInstances": 20,
                                            "priority": 1
                                        },
                                        {
                                            "zoneId": aws1,
                                            "maxNumberInstances": 10,
                                            "priority": 1
                                        }
                                    ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully added cloud zones to Rainpole project')
                else:
                    print('- Failed to add cloud zones to Rainpole project')
                    return None


def tag_vsphere_cz(cz_Ids):
    if cz_Ids is not None:
        for x in cz_Ids:
            cloudzone_id = get_right_czid_vsphere(x)
            if cloudzone_id is not None:
                api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,cloudzone_id)
                data =  {
                            "name": "vRA-Managed vSphere Compute",
                        	"tags": [
                                        {
                                            "key": "hol.cloud.zone.env",
                                            "value": "dev"
                                        },
                                        {
                                            "key": "hol.cloud.zone.platform",
                                            "value": "vsphere"
                                        }
                                    ],
                            "tagsToMatch": [
                                {
                                    "key": "compute",
                                    "value": "vsphere"
                                }
                            ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully Tagged vSphere Cloud Zone')
                    return(cloudzone_id)
                else:
                    print('- Failed to tag vSphere cloud zone')
                    return None

def tag_aws_cz_west_1(cz_Ids):
    if cz_Ids is not None:
        for x in cz_Ids:
            cloudzone_id = get_right_czid_aws_west1(x)
            if cloudzone_id is not None:
                api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,cloudzone_id)
                data =  {
                            "name": "AWS Cloud Zone / us-west-1",
                        	"tags": [
                                        {
                                            "key": "hol.zones.cloud.aws.west"
                                        },
                                        {
                                            "key": "hol.cloud.zone.env",
                                            "value": "dev"
                                        },
                                        {
                                            "key": "hol.cloud.zone.platform",
                                            "value": "aws"
                                        }
                                    ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully Tagged AWS Cloud Zone - us-west-1')
                    return cloudzone_id
                else:
                    print('- Failed to tag AWS Cloud Zone - us-west-1')
                    return None

def tag_aws_cz_west_2(cz_Ids):
    if cz_Ids is not None:
        for x in cz_Ids:
            cloudzone_id = get_right_czid_aws_west2(x)
            if cloudzone_id is not None:
                api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,cloudzone_id)
                data =  {
                            "name": "AWS Cloud Zone / us-west-2",
                        	"tags": [
                                        {
                                            "key": "hol.cloud.zone.env",
                                            "value": "prod"
                                        },
                                        {
                                            "key": "hol.cloud.zone.platform",
                                            "value": "aws"
                                        }
                                    ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully tagged AWS cloud zone - us-west-2')
                    return cloudzone_id
                else:
                    print('- Failed to tag AWS cloud zone - us-west-2')
                    return None

def tag_azure_cz(cz_Ids):
    if cz_Ids is not None:
        for x in cz_Ids:
            cloudzone_id = get_right_czid_azure(x)
            if cloudzone_id is not None:
                api_url = '{0}iaas/api/zones/{1}'.format(api_url_base,cloudzone_id)
                data =  {
                            "name": "Azure Cloud Zone / West US",
                        	"tags": [
                                        {
                                            "key": "hol.cloud.zone.platform",
                                            "value": "azure"
                                        },
                                        {
                                            "key": "hol.cloud.zone.env",
                                            "value": "dev"
                                        }
                                    ]
                        }
                response = requests.patch(api_url, headers=headers1, data=json.dumps(data), verify=False)
                if response.status_code == 200:
                    print('- Successfully tagged Azure cloud zone')
                    return cloudzone_id
                else:
                    print('- Failed to tag Azure cloud zone')
                    return None

def get_azure_regionid():
    api_url = '{0}iaas/api/regions'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        region_id = extract_values(json_data,'id')
        for x in region_id:
            api_url2 = '{0}iaas/api/regions/{1}'.format(api_url_base,x)
            response2 = requests.get(api_url2, headers=headers1, verify=False)
            if response2.status_code == 200:
                json_data2 = json.loads(response2.content.decode('utf-8'))
                region_name = extract_values(json_data2,'externalRegionId')
                compare = region_name[0]
                if compare == 'westus':
                    aws_region_id = extract_values(json_data2,'id')
                    return aws_region_id
    else:
        print('- Failed to get Azure region ID')
        return None

def create_azure_flavor():
    azure_id = get_azure_regionid()
    azure_id = azure_id[0]
    api_url = '{0}iaas/api/flavor-profiles'.format(api_url_base)
    data =  {
                "name": "azure",
                "flavorMapping": {
                    "micro": {
                        "name": "Standard_B1ls"
                    },
                    "small": {
                        "name": "Standard_B1s"
                    }
                },
                "regionId": azure_id
            }
    response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
    if response.status_code == 201:
        print('- Successfully created Azure flavor mapping')
    else:
        print('- Failed to create Azure flavor mapping')
        return None

def get_aws1_regionid():
    api_url = '{0}iaas/api/regions'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        region_id = extract_values(json_data,'id')
        for x in region_id:
            api_url2 = '{0}iaas/api/regions/{1}'.format(api_url_base,x)
            response2 = requests.get(api_url2, headers=headers1, verify=False)
            if response2.status_code == 200:
                json_data2 = json.loads(response2.content.decode('utf-8'))
                region_name = extract_values(json_data2,'externalRegionId')
                compare = region_name[0]
                if compare == 'us-west-1':
                    aws_region_id = extract_values(json_data2,'id')
                    return aws_region_id
    else:
        print('- Failed to get AWS west 1 region')
        return None

def create_aws1_flavor():
        aws_id = get_aws1_regionid()
        aws_id = aws_id[0]
        api_url = '{0}iaas/api/flavor-profiles'.format(api_url_base)
        data =  {
                    "name": "aws-west-1",
                    "flavorMapping": {
                        "micro": {
                            "name": "t2.nano"
                        },
                        "small": {
                            "name": "t2.micro"
                        }
                    },
                    "regionId": aws_id
                }
        response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
        if response.status_code == 201:
            print('- Successfully created AWS west 1 flavors')
        else:
            print('- Failed to created AWS west 1 flavors')
            return None

def get_aws2_regionid():
    api_url = '{0}iaas/api/regions'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        region_id = extract_values(json_data,'id')
        for x in region_id:
            api_url2 = '{0}iaas/api/regions/{1}'.format(api_url_base,x)
            response2 = requests.get(api_url2, headers=headers1, verify=False)
            if response2.status_code == 200:
                json_data2 = json.loads(response2.content.decode('utf-8'))
                region_name = extract_values(json_data2,'externalRegionId')
                compare = region_name[0]
                if compare == 'us-west-2':
                    aws_region_id = extract_values(json_data2,'id')
                    return aws_region_id
    else:
        print('- Failed to get AWS west 2 region ID')
        return None

def create_aws2_flavor():
        aws_id = get_aws2_regionid()
        aws_id = aws_id[0]
        api_url = '{0}iaas/api/flavor-profiles'.format(api_url_base)
        data =  {
                    "name": "aws-west-2",
                    "flavorMapping": {
                        "micro": {
                            "name": "t2.nano"
                        },
                        "small": {
                            "name": "t2.micro"
                        }
                    },
                    "regionId": aws_id
                }
        response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
        if response.status_code == 201:
            print('- Successfully created AWS west 2 flavors')
        else:
            print('- Failed to created AWS flavors')
            return None

def create_aws1_image():
        aws_id = get_aws1_regionid()
        aws_id = aws_id[0]
        api_url = '{0}iaas/api/image-profiles'.format(api_url_base)
        data =  {
                  "name" : "aws1-image-profile",
                  "description": "Image Profile for AWS1 Images",
                  "imageMapping" : {
                    "CentOS7": {
                        "name": "ami-a83d0cc8"
                    },
                    "Ubuntu": {
                        "name": "ami-1c1d217c"
                    }
                  },
                  "regionId": aws_id
                }
        response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
        if response.status_code == 201:
            print('- Successfully created AWS west 1 images')
        else:
            print('- Failed to created AWS west 1 images')
            return None

def create_aws2_image():
        aws_id = get_aws2_regionid()
        aws_id = aws_id[0]
        api_url = '{0}iaas/api/image-profiles'.format(api_url_base)
        data =  {
                  "name" : "aws2-image-profile",
                  "description": "Image Profile for AWS2 Images",
                  "imageMapping" : {
                    "CentOS7": {
                        "name": "ami-a6629ede"
                    },
                    "Ubuntu": {
                        "name": "ami-0a00ce72"
                    }
                  },
                  "regionId": aws_id
                }
        response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
        if response.status_code == 201:
            print('- Successfully created AWS west 2 images')
        else:
            print('- Failed to created AWS west 2 images')
            return None

def create_azure_image():
        azure_id = get_azure_regionid()
        azure_id = azure_id[0]
        api_url = '{0}iaas/api/image-profiles'.format(api_url_base)
        data =  {
                  "name" : "azure-image-profile",
                  "description": "Image Profile for Azure Images",
                  "imageMapping" : {
                    "Ubuntu": {
                        "name": "Canonical:UbuntuServer:16.04-LTS:latest"
                    },
                    "CentOS7": {
                        "name": "OpenLogic:CentOS:7.4:7.4.20180704"
                    }
                  },
                  "regionId": azure_id
                }
        response = requests.post(api_url, headers=headers1, data=json.dumps(data), verify=False)
        if response.status_code == 201:
            print('- Successfully created Azure images')
        else:
            print('- Failed to created Azure images')
            return None


def check_for_assigned(vlpurn):
    # this function checks the dynamoDB to see if this pod urn already has a credential set assigned

    dynamodb = boto3.resource('dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-keys')

    response = table.scan(
        FilterExpression="attribute_exists(vlp_urn)",
        ProjectionExpression="pod, vlp_urn"
    )
    urns = response['Items']
    urn_assigned = False
    for i in urns:
        if i['vlp_urn'] == vlpurn:    #This URN already has a key assigned
            urn_assigned = True

    return(urn_assigned)


def get_lab_user():
    # find out the email address of the user assigned to this HOL VLP entitlement
    assigned_account = 'URN not found in the current labs database'
    dynamodb = boto3.resource('dynamodb', aws_access_key_id=d_id, aws_secret_access_key=d_sec, region_name=d_reg)
    table = dynamodb.Table('HOL-2073-current-labs')

    response = table.scan(
        FilterExpression=Attr('vapp_urn').eq(vlp),
        ProjectionExpression="account"
    )
    accounts = response['Items']
    for i in accounts:
        assigned_account = i['account']    # get the account name (email address)

    return(assigned_account)    


##### MAIN #####
# find out if vRA is ready. if not ready we need to exit or the configuration will fail
headers = {'Content-Type': 'application/json'}
access_key = get_token()

if access_key == 'not ready':  # we are not even getting an auth token from vRA yet
    print('\n\n\nvRA is not yet ready in this Hands On Lab pod - no access token yet')
    print('Wait for the lab status to be *Ready* and then run this script again')
    sys.exit()    

headers1 = {'Content-Type': 'application/json',
           'Authorization': 'Bearer {0}'.format(access_key)}

if not vra_ready():
    print('\n\n\nvRA is not yet ready in this Hands On Lab pod - the provisioning service is not running')
    print('Wait for the lab status to be *Ready* and then run this script again')
    sys.exit()        

# vRA is ready - continue on

# check to see if this vPod was deployed by VLP (is it an active Hands on Lab?)
result = get_vlp_urn()
hol = True
if 'No urn' in result:
    # this pod was not deployed by VLP = keys must be defined at top of this file
    hol = False
    print('\n\nThis pod was not deployed as a Hands On Lab')
    try:
        # test to see if public cloud keys are included at start of script
        msg = awsid
    except:
        print('\n\n* * * *   I M P O R T A N T   * * * * *\n')
        print('You must provide AWS and Azure key sets at the top of the "2073-configure-public-cloud.py" script')
        print('Uncomment the keys, replace with your own and run the configuration batch file again')
        print('The script can be found in the "Lab Files" directory on the desktop')
        sys.exit()
else:
    vlp = result

if hol:
    #this pod is running as a Hands On Lab
    lab_user = get_lab_user()  # find out who is assigned to this lab

    # find out if this pod already has credentials assigned
    credentials_used = check_for_assigned(vlp)
    if credentials_used:
        print('\n\n\nThis Hands On Lab pod already has credentials assigned')
        print('You do not need to run this script again')
        sys.exit()
        
    assigned_pod = get_available_pod()
    if assigned_pod[0] == 'T0':
        # checking to see if any pod credentials are available
        print('\n\n\nWARNING - No Hands On Labs public cloud credentials are available now!!')
        print('There is a limited set of credentials available to share across active labs and they are all in use')
        print('Please either wait a bit and run this script again or end this lab and try again later')
        payload = { "text": f"*WARNING - There are no credential sets available for {lab_user}*" }
        send_slack_notification(payload)
        sys.exit()

    else:   
        #we have available pod credentials - let's get them
        cred_set = assigned_pod[0]
        unreserved_count = assigned_pod[1]
        available_count = assigned_pod[2]
        keys = get_creds(assigned_pod[0], vlp)

        awsid = keys['aws_access_key']
        awssec = keys['aws_secret_key']
        azsub = keys['azure_subscription_id']
        azten = keys['azure_tenant_id']
        azappkey = keys['azure_application_key']
        azappid = keys['azure_application_id']

        # build and send Slack notification
        info = ""
        info +=(f'*Credential set {cred_set} assigned to {lab_user}* \n')
        info +=(f'- There are {(available_count-1)} sets remaining out of {unreserved_count} available \n')
        payload = { "text": info }
        send_slack_notification(payload)

print('\n\nPublic cloud credentials found. Configuring vRealize Automation\n\n')

print('Creating cloud accounts')
create_aws_ca()
create_azure_ca()


print('Tagging cloud zones')
c_zones_ids = get_czids()
aws_cz1 = tag_aws_cz_west_1(c_zones_ids)
aws_cz2 = tag_aws_cz_west_2(c_zones_ids)
azure_cz = tag_azure_cz(c_zones_ids)
vsphere_cz = tag_vsphere_cz(c_zones_ids)  # really this is to rename the cloud zone but it also resets the tags

print('Udating projects')
project_ids = get_projids()
update_project(project_ids,vsphere_cz,aws_cz1,aws_cz2,azure_cz)
update_project_rp(project_ids,vsphere_cz,aws_cz1,aws_cz2,azure_cz)

print('Creating flavor profiles')
create_azure_flavor()
create_aws1_flavor()
create_aws2_flavor()

print('Creating image profiles')
create_azure_image()
create_aws1_image()
create_aws2_image()
