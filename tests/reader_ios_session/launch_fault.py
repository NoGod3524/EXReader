#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Preserve original stdin/stdout controls while executing the actual iOS binary."""
import os
import sys

def run(role):
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    binary = os.environ['EXR_IOS_' + role + '_BINARY']
    environment = dict(os.environ)
    if 'READER_TEST_AUTH' in environment:
        environment['SIMCTL_CHILD_READER_TEST_AUTH'] = environment['READER_TEST_AUTH']
    os.execvpe('xcrun', ['xcrun', 'simctl', 'spawn', os.environ['EXR_DAV_IOS_UDID'], binary, *sys.argv[1:]], environment)


if __name__ == '__main__': run('FAULT')
