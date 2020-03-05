Function Get-VlpUrn {
# determine current pods' URN (unique ID) using Main Console guestinfo
# this uses a VLP-set field named "vlp_vapp_urn"
                                Return Get-OvfEnvValue -Key 'vlp_vapp_urn'
} #End Get-VlpUrn


Function Get-OvfEnvValue {
# using Main Console guestinfo from OVFENV, pull the value associated with the specified key

                PARAM(
                                $Key = 'vlp_vapp_urn'
                )
                $tool = 'C:\Program Files\VMware\VMware Tools\vmtoolsd.exe'

                if( Test-Path $tool ) {       
                                [xml]$output = & $tool --cmd 'info-get guestinfo.ovfenv'  | Out-String
                                Try {
                                                $value = ($output.Environment.PropertySection.Property | where {$_.key -eq $Key}).value
                                                if( $value.length -gt 0 ) {
                                                                Return $value
                                                }
                                                else {
                                                                Return 'NOT REPORTED'
                                                }
                                } Catch {
                                                Return "(no access to OVF environment)"
                                }
                }
                else {
                                Return "$tool not found"
                }

} #End OvfEnvValue-VlpUrn

