# Held-out cases

Written before the verifier and any other later improvement, and **never used for tuning**.

Rules:
- Do not change these files after seeing any result on them.
- Run the final pipeline on them once per pipeline version and report every run, good or bad.
- If a case turns out to be mislabeled, say so in the report and keep the original label in the results.

Run: `docker compose exec worker python -m app.eval.run --config all --mode record --cases app/eval/heldout --detail`
