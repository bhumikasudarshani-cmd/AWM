# Testing

Standing rules for this project:

1. **TDD.** Write a failing test first, see it fail, then write the code that makes it pass, then refactor.
2. **Every feature gets unit tests and an integration test.**
3. **End-to-end check on real GitHub** before a feature counts as done.
4. **Load simulation** at the end of the project.

## Test levels

| Level | What it proves | Where |
|---|---|---|
| Unit | One function or class in isolation (parser, filters, prompt builder, JSON validation, token budget) | `tests/test_*.py` |
| Integration | Several parts together: signed webhook, queue, worker, pipeline, review payload. GitHub and the LLM are replaced by fakes; Redis by an in-memory stand-in | `tests/test_integration_*.py` |
| End-to-end | The real stack: real GitHub, real webhook delivery, real model | Manual checklist below |
| Load | Throughput, latency and failure behaviour under heavy traffic | `loadtest/` (planned, end of project) |

## Running tests

The test tools live inside the Docker image, so run them there (nothing to install on the host).

```cmd
:: Windows cmd, from the project folder
docker compose run --rm -v "%cd%\tests:/srv/tests" api python -m pytest -q
```

```powershell
# Windows PowerShell
docker compose run --rm -v "${PWD}\tests:/srv/tests" api python -m pytest -q
```

One test (`test_cross_check_with_unidiff`) is skipped unless `unidiff` is installed (`requirements-dev.txt`).

## Tests are hermetic

A test run must give the same result on every machine and must cost nothing.

- `tests/conftest.py` resets the model settings (`LLM_*`, `DUMP_FIXTURES`) for every test, so a developer's `.env`
  can never switch the paid model on. `docker compose run` loads `.env`, so this matters.
- It also blocks real network transports: a test that tries to reach the internet fails with
  "real network call attempted in a test". `httpx.MockTransport` still works.
- `tests/test_hermetic.py` checks both guards.
- Real model calls happen only in the evaluation (`python -m app.eval.run`) and in the end-to-end run, never in `pytest`.

## TDD loop

1. Write the test. Run it. It must fail, and for the right reason (not a typo).
2. Write the smallest code that passes.
3. Run the whole suite. Refactor with the tests green.
4. Add an integration test for the behaviour the feature adds to the full flow.

A test that has never failed has not proven anything. When a test is written after the code, break the code on purpose once and check that the test goes red.

## What is faked in integration tests

| Real thing | Stand-in | Why this is acceptable |
|---|---|---|
| GitHub API | `httpx.MockTransport` serving realistic responses | Deterministic, no rate limits, no token |
| LLM | A fake provider returning scripted JSON | Fast, free, lets us test bad output too |
| Redis | An in-memory object with the same calls | No server needed; the real Redis is covered by the end-to-end run |
| Queue | A recorder of `enqueue_job` calls | We call the worker function directly |

The stand-ins cannot catch problems that only appear with the real service (network errors, real rate limits, real model quality). That is what the end-to-end run is for.

## End-to-end checklist (real GitHub)

1. Docker stack and the webhook forwarder are running; `GET /health` returns ok.
2. Open a PR containing the demo file (`breakpoint()`, `shell=True`, `verify=False`, a fake password).
3. The review appears within about 15 seconds with a greeting and four inline comments on the right lines.
4. Push another commit: a new review appears and findings already posted are not repeated.
5. Open a PR with a rename, a binary file and a lockfile: nothing crashes and skipped files are listed with reasons.

## Load simulation (end of project)

"Users" here means repositories and pull requests sending webhooks. The simulation runs against a fake GitHub server and a fake LLM with realistic delays, never against the real GitHub.

Scenarios:
- Burst of thousands of webhooks, including duplicate deliveries, bad signatures, and drafts.
- Many pull requests in flight at once, with queue depth and worker throughput recorded.
- Slow or failing GitHub and LLM responses (timeouts, 5xx, rate limits) to exercise retries.

Measure:
- Webhook response time (p50, p95, p99); the target is a response well under one second.
- Time for the queue to drain, jobs per minute per worker, Redis memory.
- Correctness under load: no duplicate reviews, no lost jobs, no crashes.

Real-model speed is measured separately (seconds per review on this laptop) and used to estimate capacity. The load test shows where the system bottlenecks; it is not proof that real GitHub traffic of that size would behave the same.

## Definition of done

A feature is done when its unit tests, its integration test and its end-to-end check pass, and the documentation reflects what the code does.
