# Distributed lease benchmark

## Result snapshot

This is a finite local benchmark of the optional PostgreSQL lease store at source
revision `69b9430ce1dd92d38238696f0c74b063a386f8b8`.

| Measure | Observed value |
| --- | ---: |
| Planned tasks | 1,000 |
| Spawned Python worker processes | 4 |
| Terminal completions | 1,000 |
| Total execution attempts | 1,000 |
| Duplicate execution attempts | 0 |
| Idempotent terminal recommits | 0 |
| Expired attempts | 0 |
| Maximum attempts for one task | 1 |
| Elapsed time | 3.607 s |
| Throughput | 277.2 tasks/s |
| Lease-to-commit latency p50 | 10.46 ms |
| Lease-to-commit latency p95 | 20.16 ms |
| Maximum lease-to-commit latency | 162.33 ms |

The four workers completed 247, 252, 251, and 250 tasks. Every planned task
reached one canonical terminal record; the final queue contained zero pending,
leased, or failed tasks.

## Environment

- CPython 3.13.14 using the `spawn` multiprocessing start method
- macOS 26.6.2 on arm64
- PostgreSQL 17.11
- Official multi-architecture image pinned by digest:
  `postgres@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73`
- Five-second task leases

The exact machine-bound measurements and worker distribution are preserved in
`metrics.json`, which contains no database connection string.

## Separate crash-recovery evidence

The healthy-load run intentionally contains no worker crash. A separate integration
test spawns a worker, waits for it to acquire a lease, forcibly kills the process,
reclaims the task after expiry, rejects the killed worker's token, and verifies the
attempt history as `expired` followed by `complete`. That test runs in public CI on
Python 3.12, 3.13, and 3.14 with a real PostgreSQL service.

## Reproduction

```bash
docker compose -p agent-eval-distributed-test \
  -f docker-compose.distributed.yml up -d --wait

AGENT_EVAL_POSTGRES_DSN='postgresql://postgres:agent_eval_local@127.0.0.1:55432/agent_eval' \
uv run agent-eval-distributed-benchmark \
  --tasks 1000 \
  --workers 4 \
  --lease-seconds 5 \
  --source-revision 69b9430ce1dd92d38238696f0c74b063a386f8b8 \
  --output artifacts/distributed-benchmark/latest/metrics.json
```

Operational latency and throughput should vary across machines and runs. Semantic
acceptance is the exact task/attempt accounting and absence of duplicate terminal
commits, not reproduction of the same wall-clock measurements.

## Claim boundary

This benchmark demonstrates local multi-process coordination, PostgreSQL row
leasing, canonical terminal accounting, and measured failure fencing. It does not
establish production traffic, multi-host operation, internet scale, or a service
availability claim.
