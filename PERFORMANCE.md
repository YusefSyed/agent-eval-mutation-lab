# Local scheduler profile

This file records a diagnostic development measurement, not a cross-machine
benchmark or résumé speed claim.

## Environment and method

- Date: 2026-08-28
- Python: 3.13.14
- `uv`: 0.11.29
- Workload: the 104-task v1/v2 × evidence-condition matrix
- Repetitions: 250, or 26,000 task executions per mode
- Parallel mode: a fresh four-thread executor per repetition

## Result

| Mode | Wall time | Relative to sequential |
| --- | ---: | ---: |
| Sequential | 0.067487 s | 1.000× |
| Four threads | 0.170682 s | 2.529× |

Threads were slower because the individual scoring tasks are tiny. The result is why
`workers=1` remains the reference mode. The bounded thread backend is retained only
to test schedule independence, out-of-order completion, task isolation, and
single-writer persistence. No throughput improvement is claimed.
