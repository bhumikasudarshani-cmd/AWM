# PR Reviewer

**Verified, low-noise, measurable AI code review for GitHub pull requests.**

A self-hostable GitHub App that receives pull request events, queues review jobs, and (in progress) runs each diff through a multi-stage AI pipeline whose findings are verified against real evidence, filtered for noise, and scored against a labeled benchmark.

![status](https://img.shields.io/badge/status-Day%201%20complete-blue)
![python](https://img.shields.io/badge/python-3.12-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## Why this project

Existing AI review tools tend to fail in the same ways: noisy comments, missed bugs, shallow context, unpredictable cost, and no way to measure how accurate they actually are on *your* repository. This project is built around one thesis:

> Every comment should come with evidence, noise should shrink with team feedback, and accuracy should be measurable.

## Status

| Area | State |
|---|---|
| Webhook receiver (signature check, dedupe, queueing) | Done |
| GitHub App authentication (JWT, installation tokens, cache) | Done |
| Background worker, pull request diff retrieval | Done |
| Docker Compose setup, health endpoint, signature tests | Done |
| Diff parser and line-position mapping | In progress |
| Specialist review stages, verifier, filter | Planned |
| Posting reviews and check runs to GitHub | Planned |
| Feedback learning loop, evaluation harness, dashboard | Planned |

The worker currently fetches and logs the diff. The review pipeline plugs into `review_pull_request` in `app/workers/tasks.py`.

## How it works

```
GitHub ──webhook──▶ API (FastAPI) ──enqueue──▶ Redis ──▶ Worker (Arq)
                     │                                      │
          verify signature                       installation token (cached)
          dedupe delivery ID                     fetch pull request diff
          ignore drafts / irrelevant events      └─▶ review pipeline (next)
```

1. GitHub sends a webhook to `POST /webhooks/github`.
2. The API verifies the `X-Hub-Signature-256` HMAC and rejects invalid requests with `401`.
3. The `X-GitHub-Delivery` ID is stored in Redis (24 h), so redelivered events are ignored.
4. For `pull_request` events with action `opened`, `reopened`, `synchronize`, or `ready_for_review` (non-draft), a job is enqueued with the ID `repo#number@head_sha`, so the same commit can never be queued twice.
5. The API responds `202` immediately; the work happens in the worker.
6. The worker exchanges an App JWT for an installation token (cached in Redis for 50 minutes) and fetches the unified diff.

## Quick start

### Prerequisites

- Docker Desktop (with Docker Compose)
- Node.js (only for the Smee webhook forwarder)
- A GitHub account that can create and install GitHub Apps
- Python 3.12+ (only if you want to run tests outside Docker)

### 1. Create a GitHub App

Go to **Settings → Developer settings → GitHub Apps → New GitHub App**.

| Setting | Value |
|---|---|
| Webhook URL | Your Smee channel URL (see step 4) |
| Webhook secret | A long random string (see below) |
| Pull requests | Read and write |
| Contents | Read-only |
| Checks | Read and write |
| Issues | Read-only |
| Metadata | Read-only (automatic) |
| Subscribe to events | Pull request, Issue comment, Pull request review comment |
| Installation | Only on this account |

Generate a webhook secret:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

After creating the app, note the **App ID** (a number, not the Client ID) and click **Generate a private key** to download a `.pem` file. Then install the app on a test repository.

> **Minimum permissions today:** only *Pull requests: Read* and *Metadata* are used by the current code. The write permissions and extra events are requested now so you will not need to re-approve the app when review posting and slash commands land. Comment events are received but ignored for now.

### 2. Configure environment variables

```bash
# macOS / Linux
cp .env.example .env

# Windows (cmd or PowerShell)
copy .env.example .env
```

| Variable | Description |
|---|---|
| `GITHUB_APP_ID` | Numeric App ID from your app's settings page |
| `GITHUB_PRIVATE_KEY` | Contents of the `.pem` file on **one line**, newlines written as `\n`, wrapped in double quotes |
| `GITHUB_WEBHOOK_SECRET` | Must exactly match the secret in the GitHub App |
| `REDIS_URL` | Defaults to `redis://localhost:6379`; Docker Compose overrides it to `redis://redis:6379` |
| `AUTH_MODE` | `mock` for now; reserved for dashboard login adapters |

Convert the key to a single line:

```powershell
# Windows PowerShell (copies the result to your clipboard)
(Get-Content "$HOME\Downloads\<your-key>.pem" -Raw) -replace "`r?`n", '\n' | Set-Clipboard
```

```bash
# macOS / Linux
awk 'NF {printf "%s\\n", $0}' ~/Downloads/<your-key>.pem
```

`.env` is git-ignored. Never commit it, and never commit the `.pem` file.

### 3. Run the stack

```bash
docker compose up --build
```

This starts Redis, the API (port 8000), and the worker. Verify the API:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4. Forward webhooks to your machine

1. Create a channel at [smee.io](https://smee.io) and use its URL as the GitHub App's **Webhook URL**.
2. Run the forwarder in a second terminal (keep it open):

```bash
npx smee-client --url https://smee.io/<your-channel> --target http://localhost:8000/webhooks/github
```

### 5. Try it

Open a non-draft pull request on the repository where the app is installed. You should see:

```
api-1     | queued ...
worker-1  | diff_fetched ...
```

You can also inspect delivery status under **GitHub App → Advanced → Recent Deliveries** (`202` means accepted).

## Tests

```bash
pip install -r requirements.txt
pytest
```

Current tests cover webhook signature verification (valid, wrong secret, tampered body, missing or malformed header, empty secret).

## Project structure

```
.
├── app/
│   ├── main.py              FastAPI app, Redis and queue lifecycle, /health
│   ├── config.py            Environment-based settings
│   ├── api/
│   │   └── webhooks.py      Signature check, dedupe, enqueue
│   ├── github/
│   │   ├── signature.py     HMAC-SHA256 verification (constant-time)
│   │   └── app_auth.py      App JWT, installation tokens, Redis cache
│   └── workers/
│       └── tasks.py         review_pull_request job and worker settings
├── tests/
│   └── test_signature.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Roadmap

**Tier 1: core pipeline**
Diff parser with line-position mapping, specialist stages (security, bugs, maintainability), static-scanner evidence (Semgrep, gitleaks, linters), verifier, noise filter, PR summary with risk score, batched inline review and Check Run, initial evaluation harness.

**Tier 2: differentiators**
Feedback learning loop (reactions and dismissals tune future reviews), lightweight repository context (callers, related tests), slash commands (`/review`, `/explain`, `/ignore`), metrics dashboard (precision, recall, actionable rate, cost per review), bring-your-own-key with per-repository budget caps.

**Tier 3: stretch**
Test generation, merge simulation, self-hosting with a local LLM, dependency and CVE checks.

Success will be measured with an ablation table (baseline, specialists, evidence, verifier, filter) on a labeled benchmark, reporting precision, recall, comments per PR, and cost per PR.

## Security

- Webhook requests are rejected unless the HMAC signature is valid.
- Webhook deliveries are deduplicated; job IDs make queueing idempotent.
- Pull request content is treated as untrusted. The service does not execute code from pull requests.
- Secrets live in environment variables. Do not log tokens, keys, or repository contents.
- Restrict the GitHub App installation to the repositories that need it.
- Use HTTPS for any production webhook endpoint.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `docker info` shows no Server section | Docker Desktop is not running. Start it and wait for "Engine running". |
| `401 invalid signature` | `GITHUB_WEBHOOK_SECRET` differs from the GitHub App secret. Make them identical and restart the containers. |
| Nothing arrives in the Smee terminal | App not installed on the repository, wrong Webhook URL, or webhook not active. |
| Event received but ignored | Draft pull requests and unhandled actions or events are skipped by design. |
| `queued` appears but no `diff_fetched` | Check worker logs. Usually a private key or App ID problem. |
| `InvalidKeyError` or `Bad credentials` | The key is not on a single line with `\n` escapes, or it belongs to a different app. |
| Changes to `.env` have no effect | Restart with `docker compose up --build`. |

## Contributing

Issues and pull requests are welcome. Please keep changes focused, add tests for new behavior, and never include credentials in commits or logs.

## License

MIT. See [LICENSE](LICENSE).
