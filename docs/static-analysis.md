# Static-analysis policy

## Is Codacy used?

Not as a required grading service. The current application does not send
student uploads to Codacy and does not require a Codacy token.

Codacy's API is a repository-analysis API: its v3 endpoints address an
organization/provider/repository and expose repository, commit, pull-request,
coverage and issue resources. That is a different input contract from this
local-first application, which receives independent `.c` uploads before there
is a Git repository or commit to analyze. Sending every student submission to
a remote repository analyzer would also add network dependency, credentials,
rate limits, data-disclosure concerns and asynchronous analysis latency to the
grading path.

Codacy is therefore an optional external reporting integration for a future
Git-backed deployment, not the source of truth for grades.

## What AutoGrader uses instead

The Linux grading path records several independent evidence sources:

1. **GCC C11 diagnostics** from the isolated compile step.
2. **Validated executable tests** with explicit instructor-owned expected
   outputs.
3. **AddressSanitizer/UndefinedBehaviorSanitizer** runs when the rubric asks
   for sanitizer evidence.
4. **Deterministic source metrics** for structure, complexity estimates,
   readability and rubric-specific heuristics.
5. **Local C static-analysis tools**, executed inside the same Bubblewrap
   namespace policy and stored as non-scoring evidence:
   - Cppcheck;
   - Flawfinder;
   - Clang-Tidy.
6. **Assignment-scoped normalized fingerprints** for review-only similarity
   findings.

The local tool evidence is intentionally not an automatic point deduction. An
instructor's rubric can use explicit evidence criteria, but tool output cannot
silently change rubric weights or turn a warning into a failing grade.

## Codacy comparison

Codacy lists Clang-Tidy, Cppcheck, Flawfinder and Opengrep among its C static
analysis tools. AutoGrader uses the first three locally because they can inspect
an uploaded source file without requiring a remote repository analysis. This
provides comparable categories of C diagnostics while preserving local data
ownership. It is not a claim that AutoGrader reproduces Codacy's full product,
quality model, issue deduplication or coverage service.

## Evidence model

Local tool results appear with:

```text
source_type = static_analysis_tool
scoring_impact = false
provenance.source = local_linux_toolchain
```

Each result keeps the tool name, bounded output, exit status, duration,
timeout/truncation state and a review-oriented status. The report can therefore
show what a tool observed without confusing a tool warning with a confirmed
functional failure.
