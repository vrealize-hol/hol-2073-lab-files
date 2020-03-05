import os
import subprocess

def get_vlp_urn():
    # determine current pods' URN (unique ID) using Main Console guestinfo
    # this uses a VLP-set field named "vlp_vapp_urn" and will only work for a pod deployed by VLP

 #   tools_dir = 'C:\\Program Files\\VMware\\VMware Tools\\vmtoolsd.exe'
    
    vlp_urn = 'some-fake-urn'
    tools_location = 'C:\\windows\\system32\\nslookup.exe'

    if os.path.isfile(tools_location):
        response = subprocess.run([tools_location, 'google.com'], stdout=subprocess.PIPE)

        return response.stdout
    else:
        return "VMware tools not found"

result = get_vlp_urn()
print(result)
