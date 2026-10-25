"""Print the gate result as short log lines so root can read evidence without downloading anything."""
import json
import sys

result=json.load(open(sys.argv[1],encoding='utf-8'))
print('SUMMARY gate_accepted=%s complete_product=%s product_source=%s verifier=%s run=%s/%s'%(
      result['gate_accepted'],result['complete_product'],result['product_source'],result['verifier_source'],
      result['validation_run_id'],result['validation_attempt']))
for name,scope in result['scopes'].items():
    print('SCOPE %s %s missing=%s reasons=%s'%(name,scope['status'],','.join(scope['missing']),'|'.join(scope['reasons'])))
for item in result['entries']:
    entry=item['entry']
    print('ENTRY %s %s run=%s/%s source=%s authentic=%s status=%s reason=%s'%(entry.get('scope'),entry.get('platform',entry.get('direction')),
          entry.get('run_id'),entry.get('attempt'),entry.get('source_sha'),item['authentic'],item['status'],item['reason']))
    for art in item.get('proof',{}).get('artifacts',[]):
        print('  ZIP id=%s bytes=%s sha256=%s expires=%s members=%s name=%s programs_verified=%s'%(art['id'],art['bytes'],art['sha256'],
              art['expires_at'],art['members'],art['artifact'],art['programs_verified']))
        for row in art['binaries']:print('    BIN %s bytes=%s sha256=%s'%(row['member'],row['bytes'],row['sha256']))
for row in result['negative_controls']:
    print('NEGATIVE run=%s source=%s refused=%s reason=%s'%(row['entry'].get('run_id'),row['entry'].get('source_sha'),row['refused'],row['reason']))
for row in result['derived_controls']:print('DERIVED %s refused=%s reason=%s'%(row['name'],row['refused'],row['reason']))
for problem in result['problems']:print('PROBLEM',problem)
