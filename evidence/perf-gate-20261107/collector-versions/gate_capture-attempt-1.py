#!/usr/bin/env python3
"""E1 operation plan with a strict <5% complete-batch rule and fail-closed idle checks.

Use the same e1_capture.py arguments, with --runs >=5 --max-batches 1.
All raw operations and unsuccessful batches are preserved; no trimming or averaging.
"""
import sys
from pathlib import Path
import e1_capture as e1

original_summary = e1.summarize
original_environment = e1.environment


def summarize(trials):
    result = original_summary(trials)
    result['stable'] = (len(trials) >= 5 and bool(result['metrics']) and
                        all(t.get('idle_target_met') is True for t in trials) and
                        all(s['range_over_median_pct'] is not None and
                            s['range_over_median_pct'] < 5
                            for s in result['metrics'].values()))
    return result


def environment(args):
    if args.runs < 5 or args.max_batches != 1:
        raise ValueError('Require >=5 fresh processes and exactly one predeclared batch')
    result = original_environment(args)
    result['identities'][str(Path(__file__).resolve())] = e1.sha(__file__)
    result['gate_sampling_rule'] = 'all eight metrics range/p50 <5%; >=5 processes; unmet idle invalidates entire batch'
    return result


if __name__ == '__main__':
    e1.summarize = summarize
    e1.environment = environment
    sys.exit(e1.main())
