# Deterministic integration security baseline - September 25, 2026

This separate baseline records the 13 deterministic mock-model Docker fixtures
under the dependency environment with pytest 9.0.3. Two fresh local executions
produced byte-identical normalized reports and SQLite snapshots; the independent
full-suite verifier checked all 14 canonical files.

Compared with the preserved v1 artifacts, all fixture outcomes, dispatch records,
approval records and SQLite bytes are unchanged. Only the pyproject.toml and uv.lock
source digests differ. The verifier still requires an exact current-source match;
CI now compares current runs to this versioned baseline.

The v1 deterministic artifacts and the frozen 24-sample local-model study were not
overwritten or rerun. This validation used a mock model, synthetic state and Docker
containers with networking disabled; it made no provider inference calls.
