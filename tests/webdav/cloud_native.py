# SPDX-License-Identifier: MIT
"""Platform tools for the existing Actions-only native TLS fixtures."""
import os
import subprocess
import sys


def trust_fixture_certificates(certificates, prefix):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'fixture trust is cloud only'
    for certificate in certificates:
        if os.environ.get('EXR_DAV_IOS_UDID'):
            command = ['xcrun', 'simctl', 'keychain', os.environ['EXR_DAV_IOS_UDID'], 'add-root-cert', str(certificate)]
        elif os.name == 'nt':
            command = ['certutil', '-addstore', '-f', 'Root', str(certificate)]
        elif sys.platform == 'darwin':
            command = ['sudo', 'security', 'add-trusted-cert', '-d', '-r', 'trustRoot',
                       '-k', '/Library/Keychains/System.keychain', str(certificate)]
        else:
            command = ['sudo', 'cp', str(certificate),
                       '/usr/local/share/ca-certificates/' + prefix + certificate.name]
        subprocess.run(command, check=True, capture_output=True)
    if os.name != 'nt' and sys.platform != 'darwin':
        subprocess.run(['sudo', 'update-ca-certificates'], check=True, capture_output=True)
