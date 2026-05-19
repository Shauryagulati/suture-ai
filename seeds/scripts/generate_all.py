"""Orchestrator — run every synthetic-data generator in dependency order.

Wired into `make seed-synthetic`. Default seed is 42 (the corpus is built
and tested at this seed).

Order matters:
    1. patients      (referrals + discharges reference these)
    2. practices     (referrals reference these)
    3. referrals
    4. discharges
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STEPS = [
    "seeds.scripts.generate_patients",
    "seeds.scripts.generate_practices",
    "seeds.scripts.generate_referrals",
    "seeds.scripts.generate_discharges",
]

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all synthetic-data generators.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    for module in STEPS:
        print(f"\n→ {module} --seed {args.seed}")
        result = subprocess.run(
            [sys.executable, "-m", module, "--seed", str(args.seed)],
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            print(f"step {module} failed with exit {result.returncode}", file=sys.stderr)
            return result.returncode

    print("\nAll synthetic data generated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
