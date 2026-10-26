# Add-two-integers fixture

This fixture is intentionally small enough to run in deterministic tests and
in the real Bubblewrap-backed Linux runner. The rules explicitly define the
64-bit overflow boundary so that expected output is justified by the
assignment, not by a generated reference solution.

From `backend/`, with the real Linux runner:

```bash
AUTOGRADER_RUNNER=bubblewrap python -m app.cli \
  --assignment ../examples/add_two_integers/assignment.json \
  --submission ../examples/add_two_integers/correct.c \
  --submission ../examples/add_two_integers/buggy.c
```

For deterministic application-only tests, use the fake runner:

```bash
AUTOGRADER_RUNNER=fake python -m app.cli \
  --assignment ../examples/add_two_integers/assignment.json \
  --submission ../examples/add_two_integers/correct.c \
  --submission ../examples/add_two_integers/buggy.c
```

The fake runner does not claim to compile the uploaded C source. Docker remains
an optional legacy runner; Bubblewrap is the default real Linux runner.
