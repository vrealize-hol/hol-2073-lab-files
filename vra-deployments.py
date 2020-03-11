
import json
import requests
import urllib3
urllib3.disable_warnings()
import sys

vra_fqdn = "vr-automation.corp.local"
api_url_base = "https://" + vra_fqdn + "/"
headers = {'Content-Type': 'application/json'}

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
        return None

def get_deployments():
    err = 'no valid response'
    api_url = '{0}deployment/api/deployments'.format(api_url_base)
    response = requests.get(api_url, headers=headers1, verify=False)
    if response.status_code == 200:
        json_data = json.loads(response.content.decode('utf-8'))
        deployments = extract_values(json_data,'id')
        return deployments
    else:
        print('- Failed to get deployments')
        return err


##### MAIN #####

access_key = get_token()
headers1 = {'Content-Type': 'application/json',
           'Authorization': 'Bearer {0}'.format(access_key)}

depl = get_deployments()
if 'no valid response' in depl:
    sys.stdout.write('not ready')
else:
    sys.stdout.write('OK')

