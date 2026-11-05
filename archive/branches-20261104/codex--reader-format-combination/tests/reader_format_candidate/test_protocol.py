"""Actions-only refusal regressions for the exact contracts used by guard/strict."""
from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile
from common import actions, WORK, HERE, manifest_contract, strict_json, safe_members, owned_paths, verify_program, digest, write, artifact_metadata, artifact_body, identity


def main():
    actions(); passed = []
    valid = manifest_contract(strict_json((HERE / 'manifest-v2.json').read_bytes()))

    def refuse(name, callback):
        try:
            callback()
        except (AssertionError, ValueError, KeyError):
            passed.append(name); return
        raise AssertionError('invalid input accepted: ' + name)

    for index, item in enumerate(valid['files']):
        for field in ('bytes', 'sha256', 'url'):
            mutant = deepcopy(valid); mutant['files'][index]['source'][field] = 1 if field == 'bytes' else 'changed'
            refuse(item['id'] + '.source.' + field, lambda mutant=mutant: manifest_contract(mutant))
        mutant = deepcopy(valid); mutant['files'][index]['source']['license']['basis'] = 'changed'
        refuse(item['id'] + '.license', lambda mutant=mutant: manifest_contract(mutant))
        mutant = deepcopy(valid); mutant['files'][index]['expect']['import'] = 'failed'
        refuse(item['id'] + '.expectation', lambda mutant=mutant: manifest_contract(mutant))
    for name, change in (('missing-file', lambda m: m['files'].pop()),
                         ('extra-file', lambda m: m['files'].append(deepcopy(m['files'][0]))),
                         ('old-dataset-id', lambda m: m.__setitem__('dataset_id', 'reader-real-corpus-v1')),
                         ('old-Crowley-query', lambda m: next(r for r in m['files'] if r['id']=='rtf-crowley-policy').__setitem__('query','Policy and Procedure TTR'))):
        mutant = deepcopy(valid); change(mutant)
        refuse(name, lambda mutant=mutant: manifest_contract(mutant))
    for path in ('src/rtf.c', 'src/cbz.c', 'include/exreader.h', 'tests/reader_real_corpus/manifest.json', '.github/workflows/native.yml'):
        refuse('scope:' + path, lambda path=path: owned_paths([path]))
    refuse('duplicate-json-key', lambda: strict_json('{"a":1,"a":2}'))
    refuse('nonfinite-json', lambda: strict_json('{"a":NaN}'))
    for name in ('../escape', '/absolute', 'C:drive', 'dir\\escape', 'a//b', './relative'):
        body = io.BytesIO()
        with zipfile.ZipFile(body, 'w') as archive:
            info = zipfile.ZipInfo('placeholder'); info.filename = info.orig_filename = name
            archive.writestr(info, b'x')
        refuse('zip:' + name, lambda body=body: safe_members(zipfile.ZipFile(io.BytesIO(body.getvalue()))))
    for name in ('duplicate', 'symlink', 'expanded-limit'):
        body = io.BytesIO()
        with zipfile.ZipFile(body, 'w') as archive:
            if name == 'symlink':
                info = zipfile.ZipInfo('link'); info.external_attr = 0o120777 << 16; archive.writestr(info, b'file')
            else:
                archive.writestr('file', b'xx')
                if name == 'duplicate': archive.writestr('file', b'other')
        refuse('zip:' + name, lambda body=body, name=name: safe_members(zipfile.ZipFile(io.BytesIO(body.getvalue())), 1 if name=='expanded-limit' else 1024))
    binary = WORK / 'protocol/program.bin'; binary.parent.mkdir(parents=True, exist_ok=True); binary.write_bytes(b'actual-program-bytes')
    actual = {'bytes': binary.stat().st_size, 'sha256': digest(binary.read_bytes())}
    verify_program(binary, actual)
    refuse('fake-program-size', lambda: verify_program(binary, {**actual, 'bytes': 0}))
    refuse('fake-program-hash', lambda: verify_program(binary, {**actual, 'sha256': '0'*64}))
    own=identity(); full=f"format-windows-{own['run_id']}-{own['attempt']}"; blob=b'protocol-fixture'
    metadata={'name':full,'workflow_run':{'id':own['run_id'],'head_sha':own['source_sha']},'expired':False,
              'size_in_bytes':len(blob),'digest':'sha256:'+digest(blob),'expires_at':'2099-01-01T00:00:00Z'}
    artifact_metadata(metadata,full,own); artifact_body(metadata,blob)
    for name,change in (('name',lambda m:m.__setitem__('name',full+'-wrong-attempt')),
                        ('run',lambda m:m['workflow_run'].__setitem__('id',own['run_id']+1)),
                        ('source',lambda m:m['workflow_run'].__setitem__('head_sha','0'*40)),
                        ('expired',lambda m:m.__setitem__('expired',True)),
                        ('expiry',lambda m:m.__setitem__('expires_at','2000-01-01T00:00:00Z')),
                        ('digest',lambda m:m.__setitem__('digest','invalid')),
                        ('size',lambda m:m.__setitem__('size_in_bytes',0)),
                        ('missing-report',lambda m:m.pop('workflow_run'))):
        mutant=deepcopy(metadata); change(mutant)
        refuse('artifact:'+name,lambda mutant=mutant:artifact_metadata(mutant,full,own))
    refuse('artifact:actual-size',lambda:artifact_body({**metadata,'size_in_bytes':1},blob))
    refuse('artifact:actual-digest',lambda:artifact_body({**metadata,'digest':'sha256:'+'0'*64},blob))
    result = {'ok': True, 'rejected': len(passed), 'cases': passed, 'valid_manifest_accepted': True, 'valid_program_accepted': True}
    write(WORK / 'guard/protocol.json', result); print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
