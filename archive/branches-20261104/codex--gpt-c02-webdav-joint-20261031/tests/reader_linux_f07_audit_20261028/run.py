"""Actions-only source/evidence/native orchestration, always retaining failures."""
import sys
import lf07_contract as C


def main():
    C.actions_only()
    C.OUT.mkdir(parents=True, exist_ok=True)
    report = dict(C.identity(), audit_completed=False, linux_project_closure_accepted=False,
                  f07_accepted=False, full_six_platform_f07_accepted=False)
    try:
        report['source'] = C.guard()
        C.save(C.OUT / 'source.json', report['source'])
        if len(sys.argv) > 1 and sys.argv[1] == 'guard': return
        from lf07_evidence import authenticate
        from lf07_native import audit
        folder, inventory, frozen = authenticate()
        report['capture_authenticated'] = True
        result = audit(folder, inventory, frozen)
        report.update(audit_completed=True, linux_project_closure_accepted=result['linux_project_closure_accepted'])
        C.require(result['linux_project_closure_accepted'], 'substantive Linux project closure rejected; see raw findings')
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        C.save(C.OUT / 'result.json', report)


if __name__ == '__main__': main()
