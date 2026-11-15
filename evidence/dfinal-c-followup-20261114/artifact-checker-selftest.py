# SPDX-License-Identifier: MIT
"""Exercise the artifact verifier with original CTest XML and in-memory corruptions."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-xml', required=True, type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('artifact_verifier', ROOT / 'tools/check_dfinal_c_artifacts.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    inputs = [
        ('historical', ROOT / 'evidence/dfinal-c/actions-43648272236/model-tests.xml', False, 2),
        ('current', args.current_xml.resolve(), True, 4),
    ]
    rejected = 0
    for label, path, android_host, count in inputs:
        data = path.read_bytes()
        suite = ET.fromstring(data)
        print(f'{label} XML: path={path}, sha256={hashlib.sha256(data).hexdigest()}, root={suite.tag}')
        names = verifier.check_model_tests(data, android_host)
        assert len(names) == count
        print(f'{label}: original {count}/{count} passed; names={names}')
        for mutation in ('missing', 'failure', 'skipped', 'duplicate', 'wrong-mode'):
            changed = ET.fromstring(data)
            cases = changed.findall('testcase')
            if mutation == 'missing':
                changed.remove(cases[-1])
            elif mutation in ('failure', 'skipped'):
                ET.SubElement(cases[-1], mutation)
            elif mutation == 'duplicate':
                cases[-1].set('name', cases[0].get('name'))
            try:
                verifier.check_model_tests(ET.tostring(changed),
                                           not android_host if mutation == 'wrong-mode' else android_host)
            except AssertionError:
                rejected += 1
                print(f'{label}: {mutation} rejected')
            else:
                raise AssertionError(f'{label}: {mutation} incorrectly accepted')
    assert rejected == 10
    print('artifact checker selftest passed: 2 original CTest suites, 10 corrupt/mismatched suites rejected')


if __name__ == '__main__':
    main()
