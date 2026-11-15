"""Read-only source-to-surface coverage report; never infers a runtime pass."""
import importlib.util
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'tests/reader_a11y_windows/inventory_controls.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)
source = json.loads((OUT / 'F09-source-inventory.json').read_text(encoding='utf-8'))
surfaces = {
    'reader.c': ('main reader and optional product metadata/account/import host', ['closed', 'shelf']),
    'shell_screen.inc': ('reading toolbar and main shell', ['closed']),
    'shell_search.inc': ('full-text search', ['search']),
    'shell_settings.inc': ('reading layout/theme settings', ['settings']),
    'shell_toc.inc': ('table of contents', ['toc']),
    'shell_recent.inc': ('shelf', ['shelf']),
    'shell_annotations.inc': ('annotation editor/colors/save/delete', []),
    'shell_dictionary.inc': ('dictionary lookup/manager/vocabulary and shared WebDAV control helpers', []),
    'shell_docedit.inc': ('document editor', []),
    'shell_docedit_a11y.inc': ('document editor toolbar', []),
    'shell_docedit_find.inc': ('editor find/replace', []),
    'shell_docedit_footnote.inc': ('editor footnotes', []),
    'shell_docedit_outline.inc': ('editor outline', []),
    'shell_docedit_table_history.inc': ('editor table/history', []),
    'shell_footnotes.inc': ('reading footnote popup', []),
    'shell_opds.inc': ('OPDS source/browse/search/download', []),
    'shell_shelfmeta.inc': ('shelf metadata/organization dialog', []),
    'shell_tts.inc': ('speech playback/settings/export', []),
    'shell_sync.inc': ('WebDAV account/sync/credential controls via dictionary helpers', []),
}
for row in source['creation_sites']:
    surface, captures = surfaces[Path(row['path']).name]
    row.update(surface=surface, sampled_surface_captures=captures,
               runtime_site_mapping='missing: source creation site not uniquely mapped to runtime node',
               keyboard='missing', screen_reader='missing')

# The generic dictionary constructors also create the WebDAV controls, so retain
# every helper call site as well as the underlying CreateWindow construction.
inventory.CALL = re.compile(r'\b(dict_control|dict_card_create)\s*\(')
helpers = []
for path in sorted((ROOT / 'examples/windows').glob('shell_*.inc')):
    for row in inventory.calls(path.read_text(encoding='utf-8')):
        row.update(path=path.relative_to(ROOT).as_posix(),
                   surface=surfaces.get(path.name, (path.stem, []))[0],
                   runtime_site_mapping='missing: unopened helper-created control',
                   keyboard='missing', screen_reader='missing')
        helpers.append(row)

result = {'kind': 'source-to-runtime-surface-coverage',
          'scope': 'Windows production source; static sites are not runtime instances',
          'current_captures': 'F09-current-uia-fixed/all-controls.json',
          'creation_sites': source['creation_sites'], 'dynamic_helper_calls': helpers,
          'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                            for name in sorted({r['path'] for r in source['creation_sites'] + helpers})},
          'other_platforms': {p: 'missing current all-controls runtime rows; see F09.md'
                              for p in ['linux', 'macos', 'iphone', 'ipad', 'android']}}
(OUT / 'F09-surface-coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Accounted for %d native construction sites and %d shared-helper call sites.' %
      (len(result['creation_sites']), len(helpers)))
print('All unmapped runtime sites, unopened surfaces, keyboard and speech remain explicitly missing.')
