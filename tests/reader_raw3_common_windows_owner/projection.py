"""Exact host workflow projection plus enumerated standalone-auth entry adaptation."""
ORIGINAL = 'c4bb1feac3e2b404777810a526da43198b106723'
OLD_WORKFLOW = '.github/workflows/reader-windows-raw3-host.yml'
OLD_AUTH = 'tests/reader_windows_raw3/authenticate.py'
WORKFLOW = '.github/workflows/reader-raw3-common-windows-owner.yml'
NEW_GUARD = ('          python tests/reader_raw3_common_windows_owner/guard.py\n'
             '          python tests/reader_raw3_common_windows_owner/selftest.py\n')
AUTH_JOB = '''
  authenticate:
    needs: host
    runs-on: ubuntu-22.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Authenticate this attempt original owner ZIP and common guard
        env:
          GH_TOKEN: ${{ github.token }}
        run: python tests/reader_raw3_common_windows_owner/strict.py --run "$GITHUB_RUN_ID" --source "$GITHUB_SHA"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: windows-common-owner-authentication-${{ github.run_id }}-${{ github.run_attempt }}
          path: build/windows-owner-authentication/*.json
          if-no-files-found: warn
'''


def project_workflow(text):
    for current, original, count in (
        ('name: Common source Windows complete raw owner and receiver',
         'name: Windows actual installed raw3 host candidate', 1),
        ('branches: [codex/reader-raw3-common-integration]',
         'branches: [codex/reader-windows-raw3-candidate]', 1),
        (NEW_GUARD, '          python tests/reader_windows_raw3/guard.py\n', 1),
        (AUTH_JOB, '', 1),
    ):
        if text.count(current) != count:
            raise RuntimeError('host workflow projection count differs: ' + current)
        text = text.replace(current, original)
    return text


OLD_ENTRY = '''    run=api('/actions/runs/'+str(args.run))
    need(run['head_sha']==args.source and run['status']=='completed' and run['conclusion']=='success','Producer run identity/state')
    need(run['path']=='.github/workflows/reader-windows-raw3-host.yml','Unexpected producer workflow')
    attempt=run['run_attempt']
    jobs=api(f'/actions/runs/{args.run}/attempts/{attempt}/jobs?per_page=100')
    need(jobs['total_count']==1 and len(jobs['jobs'])==1,'Producer job set')
    job=jobs['jobs'][0]
    need(job['name']=='host' and job['conclusion']=='success' and job['head_sha']==args.source,'Producer job')
'''
NEW_ENTRY = '''    run=api('/actions/runs/'+str(args.run))
    attempt,job=common_current_producer(run,args)
'''
OLD_DELETE = '    archive.unlink()\n'
NEW_DELETE = ('    common_proof=common_source_provenance(archive,args.source,args.run,attempt,root,network_verified,peer_records_verified)\n'
              '    archive.unlink()\n')
OLD_WRITE = "    (out/'report.json').write_text(json.dumps(result,indent=2)+'\\n',encoding='utf-8')\n"
NEW_WRITE = ('    need(result["owner_reports"]==9 and result["network_receive"] is True and result["all_reading_records_FOUND"] is True,"Complete owner9/TLS/Mac11 proof required")\n'
             '    result.update(guard_kind="common-windows-owner",legacy_guard_executed=False,common_source_proof=common_proof,\n'
             '                  original_auth_body_preserved=True,standalone_auth_run_reused=False)\n' + OLD_WRITE)
AUTH_CHANGES = ((OLD_ENTRY, NEW_ENTRY), (OLD_DELETE, NEW_DELETE), (OLD_WRITE, NEW_WRITE))


def current_producer_identity(run, args, context, listing):
    def need(value, message):
        if not value:
            raise RuntimeError(message)
    attempt = int(context['attempt'])
    need(args.source == context['source_sha'] and args.run == int(context['run_id']),
         'only the actual current run/source may be authenticated')
    need(run['head_sha'] == args.source and run['run_attempt'] == attempt
         and run['status'] == 'in_progress' and run['conclusion'] is None,
         'current workflow identity/state differs')
    need(run['path'].split('@', 1)[0] == WORKFLOW, 'unexpected common owner workflow')
    rows = listing['jobs']
    need(listing['total_count'] == 2 and len(rows) == 2
         and {row['name'] for row in rows} == {'host', 'authenticate'}, 'exact current job set required')
    need(all(row['head_sha'] == args.source and row['run_attempt'] == attempt for row in rows),
         'job source/attempt differs')
    host = next(row for row in rows if row['name'] == 'host')
    authenticating = next(row for row in rows if row['name'] == 'authenticate')
    need(host['status'] == 'completed' and host['conclusion'] == 'success', 'current host did not pass')
    need(authenticating['status'] == 'in_progress' and context['job'] == 'authenticate',
         'authentication is not executing in its actual current job')
    return attempt, host


def adapt_auth(original):
    adapted = original
    for before, after in AUTH_CHANGES:
        if adapted.count(before) != 1:
            raise RuntimeError('standalone auth entry substitution count differs')
        adapted = adapted.replace(before, after, 1)
    return adapted


def project_auth(adapted):
    original = adapted
    for before, after in reversed(AUTH_CHANGES):
        if original.count(after) != 1:
            raise RuntimeError('adapted auth reverse substitution count differs')
        original = original.replace(after, before, 1)
    return original
