# Security model and residual risks

## Implemented controls

- Real execution is routed through the Bubblewrap Linux namespace runner, not
  `eval`, an LLM command, or an unsandboxed host execution path.
- Bubblewrap creates user, mount, PID, IPC, UTS and network namespaces, maps the
  process to a non-root UID/GID, exposes the compiler toolchain read-only, and
  provides only a fresh writable `/work` directory.
- The runner applies CPU, address-space, file-size, open-file, process-count,
  stack, output and wall-clock limits to compile and run steps. The parent
  process kills the entire process group on timeout.
- Uploads are restricted to `.c` files, UTF-8 content, bounded size and bounded
  batch count. Duplicate hashes and duplicate names are rejected.
- Artifact names are generated from server-side IDs. Client paths are never
  treated as host paths.
- Output and compiler diagnostics are bounded and represented as data. The UI
  renders them in text/code elements rather than injecting HTML.
- Similarity results are review evidence only. LLM output, if enabled, is
  validated and cannot alter rubric weights or score records.
- CSV export prefixes formula-like values (`=`, `+`, `-`, `@`) to reduce
  spreadsheet formula injection risk.
- Bubblewrap or GCC unavailability fails closed; the application does not run
  student code directly on the host as a fallback.

## Residual risks

Bubblewrap is a Linux isolation primitive, not a formal proof of native-code
isolation. Its security depends on kernel user namespaces, the exact mount and
resource policy, the compiler and the host. A high-risk deployment should use a
patched dedicated grading worker or VM, additional OS-level isolation,
restricted artifact retention and operational monitoring. Docker remains an
optional adapter, not a requirement of the default path.

The current first version assumes one backend worker for job ownership. A
multi-worker deployment needs database-backed claim locking before it is used in
production. The default local API also has no authentication because the
assignment explicitly asks for a local operator dashboard; do not expose it
directly to an untrusted network.
