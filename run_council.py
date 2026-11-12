import sys
import os
import time
import json
import argparse
import asyncio
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from council_orchestrator import CouncilEngine
from model_client import model_caller
from discovery_engine import TAVILY_TELEMETRY

async def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Council Deliberation & Deep-Research Engine")
    parser.add_argument(
        "--prompt",
        type=str,
        default="",
        help="Research query or directive for the Council"
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        default="",
        help="Path to a text file containing the research prompt"
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=25,
        help="Target number of web pages / papers to scrape per domain (default: 25)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Max concurrent worker tasks in WorkerPool (default: 8)"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default="",
        help="Path to run directory to resume checkpointed council run (e.g. runs/run_xxx)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="auto",
        choices=["auto", "focused", "bimodal", "comprehensive"],
        help="Council execution mode (default: auto, focused=1 room, bimodal=2 rooms, comprehensive=4 rooms)"
    )
    args = parser.parse_args()

    prompt = args.prompt.strip()
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, "r", encoding="utf-8") as pf:
            prompt = pf.read().strip()

    if not prompt and not args.resume:
        print("\n========================================================")
        print("  Multi-Agent Council Deliberation & Deep-Research CLI  ")
        print("========================================================")
        prompt = input("\nEnter your research query or strategic directive:\n> ").strip()

    if not prompt and not args.resume:
        print("Error: No prompt provided. Exiting.")
        sys.exit(1)

    start_time = time.time()
    engine = CouncilEngine(target_web_pages_per_domain=args.pages, max_workers=args.workers, execution_mode=args.mode)
    dossier = await engine.execute(user_prompt=prompt, resume_dir=args.resume or None)
    end_time = time.time()
    elapsed_sec = end_time - start_time

    # Collect and compile telemetry
    telemetry_logs = list(model_caller.call_telemetry_log)
    total_calls = len(telemetry_logs)
    provider_counts: dict = {}
    model_counts: dict = {}
    tier_counts: dict = {}
    total_tokens_est = 0
    total_actual_tokens = 0

    for entry in telemetry_logs:
        prov = entry.get("provider_used", "Unknown")
        mod = entry.get("model_used", "Unknown")
        tier = entry.get("tier", "Unknown")
        provider_counts[prov] = provider_counts.get(prov, 0) + 1
        model_counts[mod] = model_counts.get(mod, 0) + 1
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        total_tokens_est += entry.get("tokens_est", 0)
        total_actual_tokens += entry.get("actual_tokens", 0)

    telemetry_summary = {
        "timestamp": datetime.now().isoformat(),
        "execution_wall_time_seconds": round(elapsed_sec, 2),
        "execution_wall_time_formatted": f"{int(elapsed_sec // 60)}m {int(elapsed_sec % 60)}s",
        "total_model_calls": total_calls,
        "provider_breakdown": provider_counts,
        "model_breakdown": model_counts,
        "tier_breakdown": tier_counts,
        "token_metrics": {
            "estimated_tokens": total_tokens_est,
            "actual_tokens": total_actual_tokens
        },
        "tavily_api_metrics": {
            "search_calls": TAVILY_TELEMETRY.get("search_calls", 0),
            "extract_calls": TAVILY_TELEMETRY.get("extract_calls", 0),
            "total_tavily_calls": TAVILY_TELEMETRY.get("search_calls", 0) + TAVILY_TELEMETRY.get("extract_calls", 0),
            "cache_hits": TAVILY_TELEMETRY.get("cache_hits", 0),
            "blocked_by_budget": TAVILY_TELEMETRY.get("blocked_by_budget", 0),
            "queries": TAVILY_TELEMETRY.get("queries", [])
        },
        "dossier_length_chars": len(dossier)
    }

    # Save telemetry JSON
    try:
        with open("telemetry_latest.json", "w", encoding="utf-8") as f:
            json.dump(telemetry_summary, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to write telemetry_latest.json: {e}")

    print("\n========================================================")
    print("                    MISSION ACCOMPLISHED                ")
    print("========================================================")
    print(f"• Wall-Clock Execution Time:  {telemetry_summary['execution_wall_time_formatted']} ({elapsed_sec:.2f}s)")
    print(f"• Total LLM Model Calls:      {total_calls}")
    print(f"• Calls by Provider:          {provider_counts}")
    print(f"• Calls by Model:             {model_counts}")
    print(f"• Actual Tokens Consumed:     {total_actual_tokens:,} tokens")
    print(f"• Tavily Search API Calls:    {TAVILY_TELEMETRY.get('search_calls', 0)} searches, {TAVILY_TELEMETRY.get('extract_calls', 0)} extracts (Cache hits: {TAVILY_TELEMETRY.get('cache_hits', 0)}, Throttled: {TAVILY_TELEMETRY.get('blocked_by_budget', 0)})")
    print(f"• Final Dossier saved to:     final_dossier.md ({len(dossier):,} characters)")
    print(f"• Telemetry saved to:         telemetry_latest.json")
    print("========================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
