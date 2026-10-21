# PR Reviewer

Webhook receiver + GitHub App auth + queue + worker that fetches the PR diff.

## 1. GitHub App banao
GitHub > Settings > Developer settings > GitHub Apps > New GitHub App
- Webhook URL: smee.io channel URL (local dev) -> baad mein apna domain
- Webhook secret: koi random string (.env mein same rakho)
- Permissions: Pull requests (RW), Contents (R), Checks (RW), Issues (R), Metadata (R)
- Subscribe events: Pull request, Issue comment, Pull request review comment
- Generate private key (.pem) -> .env mein ek line (\n escaped) mein daalo
- App ko apni test repo par install karo

## 2. Local run
    cp .env.example .env        # values bharo
    docker compose up --build   # redis + api + worker

Webhook forward (alag terminal):
    npx smee-client --url https://smee.io/<your-channel> --target http://localhost:8000/webhooks/github

## 3. Test
    pip install -r requirements.txt
    pytest

Test repo mein PR kholo -> worker logs mein `diff_fetched` dikhna chahiye.

## Structure
    app/api/webhooks.py      verify signature, dedupe, enqueue
    app/github/signature.py  HMAC verification
    app/github/app_auth.py   App JWT -> installation token (Redis cache)
    app/workers/tasks.py     review_pull_request job (pipeline yahan plug hoga)
