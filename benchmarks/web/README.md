# Local Web Benchmarks

These fixtures contain only static fake-local requests, responses, and source
snippets. The benchmark runner performs passive analysis and never starts a
server, opens a socket, or executes fixture source code. Generated result
records belong under the ignored `benchmark-results/web/` directory.

Each case contains `challenge.json`, `environment.json`,
`expected_behavior.json`, `evaluation.json`, `captures.json`, and a `source/`
directory. R13 covers authentication, authorization, parameter behavior,
session state, file processing, JSON API behavior, business logic, and state
transition. Evaluation history is generated outside this fixture tree.
