"""Reproduce the Zami baseline drift using the preserved pre/post PR #96 DLLs."""
import ctypes as c
import json
import shutil
import subprocess
import sys

from runtime_routes import ROOT, OUT, LOCAL, progress
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as regression
sys.path.insert(0, str(ROOT / 'docs/ui/acceptance'))
from check_font_manager_host import render


def main():
    book = next(b for b in regression.read_json(ROOT / 'tools/regress/corpus.json')['books']
                if b['id'].startswith('zami-'))
    assert regression.file_hash(book['path']) == book['sha256']
    layout = regression.read_json(ROOT / 'tools/regress/layout.json')
    font = LOCAL / 'fonts/Reader.otf'
    if len(sys.argv) == 2:
        directory = LOCAL / ('history-'+sys.argv[1])
        result = render(book, str(directory / 'libexreader.dll'),
                        str(directory / 'quality-font-bridge.dll'), font, layout)
        sdk = regression.SDK(directory / 'libexreader.dll')
        document, count = c.c_void_p(), c.c_size_t()
        sdk.check('document_open', book['path'].encode('utf-8'), c.byref(document))
        chapters = sdk.dll.exr_document_chapters
        chapters.argtypes, chapters.restype = [c.c_void_p, c.POINTER(c.c_size_t)], c.c_void_p
        chapters(document, c.byref(count))
        result['document_chapter_count'] = count.value
        sdk.document_free(document)
        print(json.dumps(result, ensure_ascii=False))
        return
    previous = ROOT.parent / 'EXReader-mobi-20261108/build'
    versions = {
        'before': (previous / 'baseline/libexreader.dll', '7bc6bf94e43e035af6acba6b5fc070cb2efc294bde7a0567642c0249fffd3cdf'),
        'after': (previous / 'libexreader.dll', 'b08ddb2895e09c96902653ca69ac630b6b5de9a6963e22cb2e3a0ba0ead0fc46'),
    }
    results, identities = {}, {}
    for version, (source, expected) in versions.items():
        assert regression.file_hash(source) == expected, source
        directory = LOCAL / ('history-'+version)
        directory.mkdir(exist_ok=True)
        shutil.copy2(source, directory / 'libexreader.dll')
        shutil.copy2(LOCAL / 'g/quality-font-bridge.dll', directory / 'quality-font-bridge.dll')
        command = [sys.executable, '-X', 'utf8', __file__, version]
        run = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace')
        (OUT / f'history-zami-{version}-stderr.txt').write_text(run.stderr, encoding='utf-8')
        assert run.returncode == 0, (run.returncode, run.stderr)
        result = json.loads(run.stdout)
        assert result['status'] == 'ok'
        output = dict(schema=1, pixel_contract='sha256/visible-row-major-RGBA8/white/v1',
                      layout=layout, font_sha256=regression.file_hash(font),
                      environment=dict(system='Windows', machine='AMD64'), books=[result])
        (OUT / f'history-zami-{version}.json').write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
        results[version] = output
        identities[version] = dict(dll=str(source), sha256=expected, command=command,
                                   chapters=result['document_chapter_count'], pages=result['page_count'])
        progress(f'Historical PR #96 {version}: Zami {result["page_count"]} pages, {result["document_chapter_count"]} document chapters; preserved DLL identity verified.')
    report = dict(identities=identities, difference=regression.compare(results['before'], results['after']),
                  implementation_commit='84d59833620b57bb31e3e7739e3cfb8996b2d5ef',
                  provenance='evidence/mobi-kf8-fb2-20261108/protected-trees.json')
    (OUT / 'history-zami.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
