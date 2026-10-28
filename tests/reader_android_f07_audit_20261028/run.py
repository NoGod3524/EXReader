"""Retrospective original Android F07 capture audit, without rebuild or launch."""
import json
import sys

import af07_contract as C
from af07_evidence import obtain, replay
from af07_native import audit


def main():
    C.actions_only()
    C.OUT.mkdir(parents=True, exist_ok=True)
    report = dict(C.identity(), original_capture_replayed=False, android_static_closure_accepted=False,
                  full_six_platform_f07_accepted=False, new_runtime_execution=False, failures=[])
    try:
        report['source'] = C.guard()
        folders = obtain()
        raw, capture, inventory, images, bindings = replay(folders)
        report['original_capture_replayed'] = True
        result = audit(raw, capture, inventory, images, bindings)
        report['android_static_closure_accepted'] = result['android_static_closure_accepted']
        report['private_imports'] = {name: values for name, values in result['private_imports'].items() if values}
        report['private_header_dependencies'] = result['private_header_dependencies']
        report['image_private_imports'] = result['image_private_imports']
        report['provider_failures'] = result['provider_failures']
        C.require(result['android_static_closure_accepted'], 'Android F07 private-entry/provider criterion not met; retained exact findings')
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        C.save(C.OUT / 'summary.json', report)
        print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'guard':
        C.save(C.OUT / 'source.json', C.guard())
    else:
        main()
