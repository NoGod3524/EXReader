"""D14 unchanged action/dwell judge, explicit new-source identity projection."""
import os
from reuse import module
original = module('contract.py')
original.TARGETS['gtk'] = os.environ['GITHUB_SHA']
TARGETS = {'gtk': os.environ['GITHUB_SHA']}
SDK = original.SDK
ACTIONS, FORMATS, ROUNDS, DWELL_SECONDS = original.ACTIONS, original.FORMATS, original.ROUNDS, original.DWELL_SECONDS
digest, write, expected = original.digest, original.write, original.expected
validate, selftest = original.validate, original.selftest

if __name__ == '__main__':
    selftest()
