"""Actions-only, read-only diagnosis of a retained run's original artifact ZIP.
Records artifact identity and bytes, the original verdict and its original process
snapshots, and the ELF/APK geometry needed to interpret mappings. Executes nothing
from the artifact and changes nothing."""
import hashlib, json, os, subprocess, sys, zipfile
from pathlib import Path

RUN = '40949194972'
EXPECTED_SHA = '4d20006637e3fb0e7c9a79437fa554e5d3810837'
REPO = os.environ['GITHUB_REPOSITORY']
OUT = Path(os.environ['RUNNER_TEMP']) / 'diagnose-extract'
REPORT = Path(os.environ['RUNNER_TEMP']) / 'diagnose-report.json'


def gh(*args):
    return subprocess.check_output(['gh', *args])


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run = json.loads(gh('api', f'repos/{REPO}/actions/runs/{RUN}'))
    assert run['head_sha'] == EXPECTED_SHA and run['run_attempt'] == 1, run['head_sha']
    arts = json.loads(gh('api', f'repos/{REPO}/actions/runs/{RUN}/artifacts'))['artifacts']
    art = [a for a in arts if a['name'] == f'claude-c1-android-installed-sync-{RUN}-1']
    assert len(art) == 1 and not art[0]['expired']
    art = art[0]
    zip_path = OUT.parent / 'original.zip'
    zip_path.write_bytes(gh('api', f'repos/{REPO}/actions/artifacts/{art["id"]}/zip'))
    data = zip_path.read_bytes()
    report = dict(run=RUN, run_head_sha=run['head_sha'], run_conclusion=run['conclusion'], artifact_id=art['id'],
                  artifact_name=art['name'], api_size_in_bytes=art['size_in_bytes'], api_digest=art.get('digest'),
                  downloaded_bytes=len(data), downloaded_sha256=hashlib.sha256(data).hexdigest(),
                  executed_artifact_content=False)
    OUT.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        for name in names:
            target = (OUT / name).resolve()
            assert target.is_relative_to(OUT.resolve()) and not name.startswith('/'), name
        z.extractall(OUT)
    report['members'] = len(names)
    report['member_sample'] = names[:60]

    def find(suffix):
        hits = [p for p in OUT.rglob('*') if p.is_file() and p.as_posix().endswith(suffix)]
        assert len(hits) == 1, (suffix, hits)
        return hits[0]
    result = json.loads(find('c1-installed-sync/installed-sync-result.json').read_text())
    report['original_verdict'] = dict(passed=result['passed'], failures=result['failures'], source_sha=result['source_sha'],
        gates={k: v['passed'] for k, v in result['gates'].items()})
    snaps = json.loads(find('device/process-snapshots.json').read_text())
    report['original_snapshots'] = [{k: v for k, v in s.items() if k != 'net_tcp'} for s in snaps['snapshots']]
    report['original_poll_errors'] = snaps['poll_errors']
    report['original_snapshot_keys'] = sorted({k for s in snaps['snapshots'] for k in s})
    report['original_gate_detail'] = {k: result['gates'][k]['detail'] for k in result['gates'] if k.startswith('live_process')}
    lib = find('device/apk-libs/libexreader_product.so')
    apk = find('device/installed-host.apk')
    raw = apk.read_bytes()
    with zipfile.ZipFile(apk) as z:
        info = z.getinfo('lib/x86_64/libexreader_product.so')
        n = int.from_bytes(raw[info.header_offset + 26:info.header_offset + 28], 'little')
        e = int.from_bytes(raw[info.header_offset + 28:info.header_offset + 30], 'little')
        start = info.header_offset + 30 + n + e
        report['apk_entry'] = dict(compress_type=info.compress_type, compress_size=info.compress_size, file_size=info.file_size,
                                   header_offset=info.header_offset, data_start=start, data_start_mod_4096=start % 4096)
    elf = lib.read_bytes()
    phoff = int.from_bytes(elf[0x20:0x28], 'little'); phentsize = int.from_bytes(elf[0x36:0x38], 'little'); phnum = int.from_bytes(elf[0x38:0x3a], 'little')
    loads = []
    for i in range(phnum):
        o = phoff + i * phentsize
        ptype, flags = int.from_bytes(elf[o:o + 4], 'little'), int.from_bytes(elf[o + 4:o + 8], 'little')
        if ptype == 1:
            loads.append(dict(flags=flags, executable=bool(flags & 1), p_offset=int.from_bytes(elf[o + 8:o + 16], 'little'),
                              p_vaddr=int.from_bytes(elf[o + 16:o + 24], 'little'), p_filesz=int.from_bytes(elf[o + 32:o + 40], 'little'),
                              p_align=int.from_bytes(elf[o + 48:o + 56], 'little')))
    report['product_elf_sha256'] = hashlib.sha256(elf).hexdigest()
    report['product_elf_pt_load'] = loads
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    assert report['original_verdict']['source_sha'] == EXPECTED_SHA


if __name__ == '__main__':
    main()
