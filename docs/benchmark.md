# Benchmark record

No representative Ollama benchmark was claimed for the initial build. The
Linux toolchain uses Bubblewrap/GCC; Docker is optional and is not part of the
default benchmark path. The deterministic backend test suite
completed 20 tests in approximately 42 seconds on the container, including API
and fake-runner evaluation tests; that is a test-suite observation, not an
ordinary batch-evaluation SLA.

When the real environment is available, record:

- host CPU/RAM, kernel version and Bubblewrap/GCC versions;
- Ollama endpoint, model and options, or `none` for deterministic mode;
- batch size and number of validated tests per submission;
- runner/model concurrency;
- p50/p95 total evaluation time and stage timings;
- timeout, unavailable-tool and retry counts.

Do not promise the assignment's under-10-minute target without measuring the
configured workload.
