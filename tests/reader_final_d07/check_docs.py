"""D07 Actions-only source trace and Markdown link audit; never executes product code."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from markdown_it import MarkdownIt

BASE = '0889f7d1e9a537c6c1b05456547e016b26e1cd85'
DOC = Path('docs/reader-final-d07')
OUT = Path('build/reader-final-d07/payload')
MD = MarkdownIt()
REQUIRED = {'base_ancestor', 'exclusive_paths', 'protected_tree', 'fixed_source_files',
            'source_inventory_complete', 'markdown_links', 'external_responses',
            'negative_broken_link', 'negative_missing_source', 'github_chinese_slugs'}

def git(*args):
    return subprocess.check_output(['git', *args])

def allowed(path):
    return path.startswith(('tests/reader_final_d07/', 'docs/reader-final-d07/')) or path in (
        '.github/workflows/reader-final-d07.yml', 'docs/validation/reader-final-d07.json', 'HANDOFF-RESULT.md')

def heading_slugs(text):
    tokens = MD.parse(text)
    headings = []
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            children = tokens[i + 1].children or []
            headings.append(''.join(x.content for x in children if x.type in ('text', 'code_inline', 'html_inline')))
    return json.loads(subprocess.check_output(['node', 'tests/reader_final_d07/slug.mjs'],
                                             input=json.dumps(headings).encode()))

def links(text):
    for token in MD.parse(text):
        for child in token.children or []:
            if child.type == 'link_open':
                yield child.attrGet('href')
            if child.type == 'image':
                yield child.attrGet('src')

def local_link(origin, href):
    parsed = urllib.parse.urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return False
    target = origin.parent / urllib.parse.unquote(parsed.path) if parsed.path else origin
    target = target.resolve()
    assert target.is_relative_to(Path.cwd()), 'link escapes checkout'
    assert target.is_file(), 'missing relative target: ' + href
    if parsed.fragment:
        assert target.suffix == '.md', 'anchor on non-Markdown file'
        assert urllib.parse.unquote(parsed.fragment) in heading_slugs(target.read_text()), 'missing anchor: ' + href
    return True

def inventory_check(value, guide):
    rows = value['rows']
    ids = [row['id'] for row in rows]
    tags = re.findall(r'<!-- source: (G\d+) -->', guide)
    assert len(ids) == len(set(ids)) == 17 and set(ids) == {'G%02d' % n for n in range(1, 18)}
    assert len(tags) == len(set(tags)) and set(tags) == set(ids)
    for row in rows:
        for key in ('platform', 'variant', 'operation', 'paths', 'evidence', 'manual'):
            assert row.get(key), 'missing source field ' + key
        assert all(p for p in row['paths'])
        assert all(p in row['paths'] and needle for p, needle in row['needles'])

def external(url):
    record = {'url': url, 'method': 'GET', 'content_or_function_accepted': False}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EXReader-D07-document-audit'})
        with urllib.request.urlopen(req, timeout=45) as response:
            record.update(status=response.status, final_url=response.url, classification='http_response')
            assert response.status == 200
            record['ok'] = True
    except urllib.error.HTTPError as error:
        record.update(status=error.code, classification='http_error', ok=False)
    except (urllib.error.URLError, TimeoutError) as error:
        record.update(classification='network_failure', error=str(error), ok=False)
    return record

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'fixed_source': BASE,
              'sdk_source': 'edddc463c06ed5731195cdb8f06b2df6dff7699e',
              'sdk_identity': '3.41.0/ABI1/core3.40.0 (documented, not executed)',
              'program': 'Python D07 document checker; no EXReader binary', 'target': 'ubuntu-22.04',
              'product_accepted': False, 'complete_product': False, 'accepted': False,
              'guide_reviewed': False, 'links_accepted': False, 'checks': [], 'external': [],
              'sources': [], 'files': {}, 'errors': []}
    def case(name, function):
        try:
            function()
            report['checks'].append({'name': name, 'ok': True})
        except Exception as error:
            report['checks'].append({'name': name, 'ok': False, 'error': str(error)})
            report['errors'].append(name + ': ' + str(error))
    def expect(value, message):
        assert value, message
    case('base_ancestor', lambda: subprocess.check_call(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD']))
    changed = git('diff', '--name-only', BASE, 'HEAD').decode().splitlines()
    case('exclusive_paths', lambda: expect(changed and all(map(allowed, changed)), str(changed)))
    def protected():
        def tree(ref):
            return {line.split('\t', 1)[1]: line.split('\t', 1)[0] for line in git('ls-tree', '-r', ref).decode().splitlines()}
        before, after = tree(BASE), tree('HEAD')
        assert {p: v for p, v in before.items() if not allowed(p)} == {p: v for p, v in after.items() if not allowed(p)}
    case('protected_tree', protected)
    inventory = json.loads((DOC / 'source-inventory.json').read_text())
    guide = (DOC / 'guide.zh-CN.md').read_text()
    case('source_inventory_complete', lambda: inventory_check(inventory, guide))
    def sources():
        assert inventory['fixed_source'] == BASE
        for row in inventory['rows']:
            for path in row['paths']:
                raw = git('show', BASE + ':' + path)
                for needle_path, needle in row['needles']:
                    if needle_path == path:
                        assert needle in raw.decode(), row['id'] + ': missing ' + needle
                report['sources'].append({'id': row['id'], 'source': BASE, 'path': path,
                                          'sha256': hashlib.sha256(raw).hexdigest()})
    case('fixed_source_files', sources)
    urls = set()
    def markdown():
        count = 0
        for path in sorted(DOC.glob('*.md')):
            for href in links(path.read_text()):
                if not local_link(path, href):
                    assert href.startswith('https://'), 'non HTTPS external link'
                    urls.add(href)
                count += 1
        report['links_total'] = count
        assert count > 0
    case('markdown_links', markdown)
    def responses():
        assert urls, 'external list empty'
        report['external'] = [external(url) for url in sorted(urls)]
        assert all(row['ok'] for row in report['external']), 'unreachable links; raw classification preserved'
    case('external_responses', responses)
    def broken():
        for href in ('missing-d07-file.md', '#不存在的锚点'):
            try:
                local_link(DOC / 'guide.zh-CN.md', href)
            except AssertionError:
                continue
            raise AssertionError('bad link accepted: ' + href)
    case('negative_broken_link', broken)
    def missing_source():
        bad = copy.deepcopy(inventory)
        bad['rows'][0]['paths'] = []
        try:
            inventory_check(bad, guide)
        except AssertionError:
            return
        raise AssertionError('missing source accepted')
    case('negative_missing_source', missing_source)
    case('github_chinese_slugs', lambda: expect(heading_slugs('# 中文标题\n# 中文标题\n# 自有 WebDAV\n') ==
         ['中文标题', '中文标题-1', '自有-webdav'], 'Chinese or duplicate slug differs'))
    names = [row['name'] for row in report['checks']]
    assert len(names) == len(set(names)) and set(names) == REQUIRED
    # Include exact authoring inputs; copies are generated only inside Actions.
    inputs = sorted(DOC.glob('*')) + sorted(Path('tests/reader_final_d07').glob('*')) + [Path('.github/workflows/reader-final-d07.yml')]
    for path in inputs:
        if path.is_file():
            raw = path.read_bytes()
            dest = OUT / 'inputs' / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            report['files'][str(path)] = hashlib.sha256(raw).hexdigest()
    report['steps_total'] = len(inventory['rows'])
    report['source_checked'] = len(report['sources'])
    report['guide_reviewed'] = all(row['ok'] for row in report['checks'] if row['name'] in ('fixed_source_files', 'source_inventory_complete'))
    report['links_accepted'] = all(row['ok'] for row in report['checks'] if row['name'] in ('markdown_links', 'external_responses'))
    report['accepted'] = not report['errors']
    report['review_scope'] = 'source labels/contracts and link audit only; no runtime or product grant'
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['accepted'] else 1

if __name__ == '__main__':
    sys.exit(main())
