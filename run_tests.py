#!/usr/bin/env python3
"""
Test runner — orchestrates multiple voice bot calls against the AI agent.

Usage:
    # Run ALL scenarios (18 calls):
    python run_tests.py

    # Run specific scenarios:
    python run_tests.py --scenarios new_patient_scheduling prescription_refill

    # Run with shorter wait between calls:
    python run_tests.py --wait 60

    # List available scenarios:
    python run_tests.py --list
"""

import argparse
import asyncio
import logging
import sys
import time

import httpx

from scenarios import SCENARIOS, list_scenario_ids
from call_manager import get_call_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_runner")


async def wait_for_completion(call_sid: str, timeout: int = 180) -> str:
    """Poll Twilio until the call reaches a terminal state."""
    start = time.time()
    terminal = {"completed", "failed", "busy", "no-answer", "canceled"}

    while time.time() - start < timeout:
        try:
            status = get_call_status(call_sid)
            if status in terminal:
                return status
        except Exception:
            pass
        await asyncio.sleep(5)

    return "timeout"


async def run_scenario(
    client: httpx.AsyncClient,
    base_url: str,
    scenario: dict,
    index: int,
    total: int,
) -> dict:
    """Run a single test scenario and return the result."""
    print(f"\n{'='*64}")
    print(f"  [{index}/{total}] {scenario['name']}")
    print(f"  {scenario['description']}")
    print(f"{'='*64}")

    start = time.time()

    try:
        resp = await client.post(
            f"{base_url}/make-call",
            json={"scenario_id": scenario["id"]},
        )
        resp.raise_for_status()
        data = resp.json()
        call_sid = data["call_sid"]
        print(f"  Call SID : {call_sid}")
        print(f"  Waiting for call to complete...")

        status = await wait_for_completion(call_sid, timeout=180)
        elapsed = time.time() - start

        print(f"  Status   : {status}")
        print(f"  Duration : {elapsed:.0f}s")

        return {
            "scenario_id": scenario["id"],
            "call_sid": call_sid,
            "status": status,
            "elapsed": elapsed,
        }

    except httpx.HTTPStatusError as exc:
        print(f"  ERROR: {exc.response.status_code} — {exc.response.text}")
        return {
            "scenario_id": scenario["id"],
            "call_sid": None,
            "status": "error",
            "error": str(exc),
        }
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return {
            "scenario_id": scenario["id"],
            "call_sid": None,
            "status": "error",
            "error": str(exc),
        }


async def run_all(
    scenarios: list[dict],
    base_url: str,
    wait_between: int,
) -> None:
    """Run all selected scenarios sequentially."""
    total = len(scenarios)
    results: list[dict] = []

    print(f"\nStarting {total} test call(s) against {base_url}")
    print(f"Target: Pretty Good AI test line (+1-805-439-8008)\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Quick health check
        try:
            health = await client.get(f"{base_url}/health")
            health.raise_for_status()
            print(f"Server OK — public URL: {health.json().get('public_url')}\n")
        except Exception:
            print("ERROR: Cannot reach the voice bot server.")
            print(f"Make sure it's running: python main.py")
            sys.exit(1)

        for i, scenario in enumerate(scenarios, 1):
            result = await run_scenario(client, base_url, scenario, i, total)
            results.append(result)

            # Pause between calls (Twilio rate limiting + natural spacing)
            if i < total:
                print(f"\n  Pausing {wait_between}s before next call...")
                await asyncio.sleep(wait_between)

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  TEST RUN SUMMARY")
    print(f"{'='*64}")

    succeeded = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] != "completed")

    for r in results:
        icon = "OK" if r["status"] == "completed" else "FAIL"
        print(f"  [{icon:>4}] {r['scenario_id']:<30} — {r['status']}")

    print(f"\n  Completed: {succeeded}/{total}   Failed: {failed}/{total}")
    print(f"  Transcripts saved in: transcripts/")
    print(f"{'='*64}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run voice bot test calls against Pretty Good AI"
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        help="Specific scenario IDs to run (default: all)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8765",
        help="Base URL of the voice bot server (default: http://localhost:8765)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=15,
        help="Seconds to wait between calls (default: 15)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable scenarios:\n")
        for s in SCENARIOS:
            print(f"  {s['id']:<30} — {s['name']}")
        print()
        return

    # Select scenarios
    if args.scenarios:
        all_ids = set(list_scenario_ids())
        selected = []
        for sid in args.scenarios:
            if sid not in all_ids:
                print(f"Unknown scenario: {sid}")
                print(f"Available: {', '.join(sorted(all_ids))}")
                sys.exit(1)
            selected.append(next(s for s in SCENARIOS if s["id"] == sid))
    else:
        selected = SCENARIOS

    asyncio.run(run_all(selected, args.url, args.wait))


if __name__ == "__main__":
    main()
