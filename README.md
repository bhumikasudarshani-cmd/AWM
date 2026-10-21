# AWM

**Verified, low-noise, measurable AI code review for GitHub pull requests.**

PR Reviewer is a self-hostable GitHub App that analyzes pull request diffs for bugs, security vulnerabilities, and maintainability issues. Unlike general-purpose AI reviewers, it treats every finding as a claim that must be backed by evidence, filters out noise using team feedback, and reports its own accuracy on a labeled benchmark.

---

## Overview

AI code review tools commonly suffer from the same problems: noisy comments that teams learn to ignore, real bugs that slip through, shallow understanding of the surrounding codebase, unpredictable costs, and no objective way to measure accuracy on a given repository.

PR Reviewer is designed around a single principle:

> Every comment should come with evidence, noise should shrink as the team gives feedback, and accuracy should be measurable.

## Key Capabilities

- **Multi-stage review pipeline.** Specialized reviewers for security, correctness, and maintainability run independently and in parallel.
- **Evidence-backed findings.** Static analysis results (for example Semgrep, gitleaks, and linters) are attached to candidate findings, and a dedicated verifier stage confirms or rejects each one before anything is posted.
- **Precision-first filtering.** Confidence thresholds, deduplication, and per-PR comment caps keep reviews short and actionable.
- **Feedback learning.** Reactions, dismissals, and `/ignore` commands adjust future reviews for each repository.
- **Repository-aware context.** Reviews consider callers, related files, tests, and repository-specific rules, not just the raw diff.
- **Measurable quality.** A built-in evaluation harness reports precision, recall, comments per PR, and cost per review against a labeled dataset.
- **Cost control and privacy.** Bring-your-own API key, per-repository budgets, and support for self-hosting.
- **GitHub-native experience.** Summaries, risk scores, inline comments with one-click suggestion blocks, and Check Runs.

## Architecture

```
GitHub ──webhook──▶ API (FastAPI) ──enqueue──▶ Redis ──▶ Worker (Arq)
                     │                                      │
          verify signature                       authenticate as GitHub App
          deduplicate deliveries                 fetch diff and repository context
          filter irrelevant events                         │
                                                            ▼
                                                    Review pipeline
                                                            │
                                                            ▼
                                          Reviews, comments, and Check Runs on GitHub
```

The system is event-driven. The API acknowledges webhooks immediately and hands work to background workers, so review latency never blocks GitHub. Webhook deliveries are deduplicated, and jobs are keyed by repository, pull request, and commit SHA, which makes processing idempotent.

### Review pipeline

| Stage | Purpose |
|---|---|
| Preprocess | Filter generated, vendored, and binary files; chunk the diff; map lines to diff positions |
| Evidence | Run static analyzers on changed files and normalize their output |
| Specialists | Security, bug, and maintainability reviewers produce candidate findings with high recall |
| Verifier | Confirms each candidate against evidence and context, and assigns a confidence score |
| Filter | Applies confidence thresholds, deduplication, learned suppressions, and comment caps |
| Aggregator | Produces the pull request summary and risk score |
| Publisher | Posts one batched review and a Check Run |

Each stage implements a common interface, so stages can be added, swapped, or disabled per repository and evaluated independently.

### Finding format

Every finding is structured and schema-validated:

```json
{
  "file": "src/auth.py",
  "line_start": 42,
  "line_end": 45,
  "category": "security",
  "severity": "high",
  "confidence": 0.86,
  "title": "SQL injection via string formatting",
  "explanation": "User input is interpolated directly into the query string.",
  "evidence": [{ "tool": "semgrep", "rule": "python.sqlalchemy.injection" }],
  "suggested_fix": "Use a parameterized query."
}
```

## Technology

| Layer | Technology |
|---|---|
| API | Python, FastAPI |
| Queue and cache | Redis, Arq |
| Database | PostgreSQL |
| GitHub integration | GitHub App (JWT and installation tokens), webhooks, Checks API |
| Code analysis | tree-sitter, Semgrep, gitleaks, language linters |
| LLM access | Provider-agnostic abstraction (cloud or local models) |
| Packaging | Docker, Docker Compose |
| Quality | pytest, GitHub Actions |

## Configuration

Runtime settings are supplied through environment variables:

| Variable | Description |
|---|---|
| `GITHUB_APP_ID` | Numeric ID of the GitHub App |
| `GITHUB_PRIVATE_KEY` | App private key (PEM), single line with `\n` escapes |
| `GITHUB_WEBHOOK_SECRET` | Shared secret used to verify webhook signatures |
| `REDIS_URL` | Redis connection URL |
| `AUTH_MODE` | Dashboard authentication adapter |

Per-repository behavior is controlled with a `.prreview.yml` file:

```yaml
version: 1
stages: [security, bugs, maintainability]
ignore_paths: ["**/*.lock", "migrations/**"]
min_severity: medium
min_confidence: 0.7
max_comments: 12
rules:
  - "Payment handlers must use idempotency keys"
budget:
  monthly_usd: 10
```

Plain-English `rules` are given to the reviewers, which allows teams to encode conventions and business rules that static tools cannot see.

## Evaluation

Quality claims are backed by measurement. The evaluation harness replays the pipeline against a labeled set of pull requests (planted defects, real bug-introducing changes, and clean changes) and reports:

- Precision, recall, and F1
- Comments per pull request
- Actionable rate from real usage
- Cost and latency per review

Each pipeline component is evaluated in an ablation study, so its contribution to precision, recall, and noise is documented rather than assumed.

## Project Structure

```
.
├── app/
│   ├── main.py              Application entry point and health endpoint
│   ├── config.py            Environment-based settings
│   ├── api/
│   │   └── webhooks.py      Webhook intake, verification, deduplication, queueing
│   ├── github/
│   │   ├── signature.py     HMAC-SHA256 signature verification
│   │   └── app_auth.py      GitHub App JWT and installation token handling
│   └── workers/
│       └── tasks.py         Background review jobs
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Security

- Webhook requests are rejected unless the HMAC signature is valid, and comparison is constant-time.
- Deliveries are deduplicated and jobs are idempotent.
- Pull request content is treated as untrusted input. The service never executes code from pull requests, and model output is validated against a strict schema.
- Installation tokens are short-lived and cached with a safe expiry margin.
- Secrets are read from the environment and are never logged.
- The GitHub App requests only the permissions its features require and can be restricted to selected repositories.

## License

Released under the [MIT License](LICENSE).
