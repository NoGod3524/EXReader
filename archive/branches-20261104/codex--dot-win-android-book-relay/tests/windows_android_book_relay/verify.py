"""Same-run source and chained artifact authentication; no old green substitution."""
import hashlib,json,os
from pathlib import Path
import relay
root=Path('build/collected');run=os.environ['GITHUB_RUN_ID'];attempt=os.environ['GITHUB_RUN_ATTEMPT']
def artifact(prefix):return root/(prefix+'-'+run+'-'+attempt)
a=artifact('relay-windows-first')/'state.json';b=artifact('relay-android')/'state.json';c=artifact('relay-windows-return')/'state.json'
first,ha=relay.load(a,'windows-first');middle,hb=relay.load(b,'android');last,hc=relay.load(c,'windows-return')
assert middle['previous_sha256']==ha and last['previous_sha256']==hb
for k in ('original_sha256','original_bytes','book_identity'):
 assert first['data'][k]==middle['data'][k]==last['data'][k]
assert first['data']['program']['sha256']==last['data']['program']['sha256']
assert middle['data']['location']==last['data']['expected_location']
assert first['data']['location']['head']!=middle['data']['location']['head']
package=artifact('relay-windows-package');manifest=json.loads((package/'build.json').read_text())
assert manifest['source_sha']==os.environ['GITHUB_SHA']
assert hashlib.sha256((package/'EXReader/EXReader.exe').read_bytes()).hexdigest()==last['data']['program']['sha256']

# Upload flattening can put the retained C09 report at the common ancestor;
# require the original report by its accepted field rather than replacing it.
reports=[json.loads(p.read_text()) for p in artifact('relay-windows-retained').rglob('report.json')]
assert any(r.get('accepted') is True and r.get('source_sha')==os.environ['GITHUB_SHA'] for r in reports),'retained Windows gate missing'
report=dict(**relay.identity(),passed=True,phases=[{'phase':s['phase'],'checks':s['data']['checks'],'program':s['data']['program']} for s in (first,middle,last)],state_sha256=[ha,hb,hc],original_sha256=first['data']['original_sha256'],transport='authenticated staged HTTPS state transfer, not simultaneous hosts',android='API34 x86_64 emulator, not physical device',screen_reader=False)
Path('build/relay-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
