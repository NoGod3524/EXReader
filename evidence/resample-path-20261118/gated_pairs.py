"""Use bench_real_doc unchanged, retrying its fail-closed idle gate in place."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import bench_real_doc as bench

wait = bench.wait_idle


def retry_idle(threshold, timeout):
    while True:
        value = wait(threshold, min(timeout, 60))
        if value is not None:
            return value
        print('CPU idle gate closed; retrying without a sample', flush=True)


bench.wait_idle = retry_idle
if __name__ == '__main__':
    raise SystemExit(bench.main())
