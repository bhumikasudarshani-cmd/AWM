"""Command line: python -m app.eval.run --config all --mode record

Run it inside the worker container so it sees the same .env as the bot:
    docker compose exec worker python -m app.eval.run --config all --mode record
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.config import settings
from app.eval.cases import load_cases
from app.eval.gate import GATE_MAX_INPUT_TOKENS, check_gate, load_baseline
from app.eval.provider import CachingProvider
from app.eval.report import format_details, format_sweep, to_markdown
from app.eval.runner import CONFIG_NAMES, run_configs_detailed

HERE = Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate the reviewer on the labeled cases.")
    p.add_argument("--config", default="all", help="rules, llm, rules+llm, or all")
    p.add_argument("--mode", default="replay", choices=["live", "record", "replay"],
                   help="replay uses saved model answers (free, offline); record saves new ones")
    p.add_argument("--detail", action="store_true", help="list every case that was not perfect")
    p.add_argument("--model", default=None, help="model name to use (replay needs the one the answers were recorded with)")
    p.add_argument("--cases", default=str(HERE / "cases"))
    p.add_argument("--cache", default=str(HERE / "recorded"))
    p.add_argument("--out", default=str(HERE / "results"))
    p.add_argument("--gate", action="store_true",
                   help="CI mode: replay the recordings on the dev cases and exit 1 if precision or recall fell below the baseline")
    p.add_argument("--baseline", default=str(HERE / "baseline.json"))
    args = p.parse_args(argv)
    if args.gate:
        if args.mode != "replay" or args.config != "all":
            p.error("--gate needs --mode replay and --config all")
        if Path(args.cases).resolve() != (HERE / "cases").resolve():
            p.error("--gate runs on the dev cases only; the held-out cases are run by hand, once per pipeline version")
        if args.model:
            p.error("--gate uses the model named in the baseline; do not pass --model")
    return args


async def main_async(args: argparse.Namespace) -> None:
    names = list(CONFIG_NAMES) if args.config == "all" else [args.config]
    needs_model = any("llm" in n for n in names)
    provider = None
    inner = None
    baseline = None
    if args.gate:
        try:
            baseline = load_baseline(args.baseline)
        except (OSError, ValueError) as e:
            raise SystemExit(f"Gate: cannot read the baseline {args.baseline}: {e}") from e
    model_name = baseline.model if baseline else (args.model or settings.llm_model)
    max_input_tokens = GATE_MAX_INPUT_TOKENS if baseline else settings.llm_max_input_tokens
    if needs_model:
        if args.mode != "replay":
            from app.llm.openai_compat import OpenAICompatProvider

            inner = OpenAICompatProvider(settings.llm_base_url, model_name, settings.llm_api_key,
                                         timeout=settings.llm_timeout)
        provider = CachingProvider(inner, args.cache, mode=args.mode, model=model_name)

    cases = load_cases(args.cases)
    try:
        summaries, results = await run_configs_detailed(cases, names, provider, max_input_tokens=max_input_tokens,
                                      timeout=settings.llm_timeout)
    finally:
        if provider is not None:
            await provider.close()

    print(f"\nModel: {provider.model if provider else 'n/a'}   mode: {args.mode}   cases: {len(cases)} "
          f"({sum(1 for c in cases if c.is_clean)} clean)\n")
    print(to_markdown(summaries))
    if args.detail:
        print("\nCases that were not perfect:\n")
        print(format_details(results))
        print("\n" + format_sweep(results))
        for name, s in summaries.items():
            if s.mean_conf_correct is not None or s.mean_conf_wrong is not None:
                fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
                print(f"  {name}: average confidence of correct comments {fmt(s.mean_conf_correct)}, of wrong comments {fmt(s.mean_conf_wrong)}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.mode}.json"
    path.write_text(json.dumps({
        "model": provider.model if provider else None, "mode": args.mode, "cases": len(cases),
        "summaries": {k: asdict(v) for k, v in summaries.items()},
    }, indent=2), encoding="utf-8")
    print(f"\nSaved {path}")

    if baseline is not None:
        problems = check_gate(summaries, baseline)
        if problems:
            print("\nGate: FAILED\n" + "\n".join(f"  - {m}" for m in problems))
            sys.exit(1)
        print("\nGate: ok")


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
