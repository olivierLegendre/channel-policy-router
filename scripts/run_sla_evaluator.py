import argparse
import json

from channel_policy_router.main import create_use_cases
from channel_policy_router.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SLA breaches in batch")
    parser.add_argument("--limit", type=int, default=100, help="Max commands to evaluate")
    args = parser.parse_args()

    use_cases = create_use_cases(Settings())
    result = use_cases.evaluate_sla_batch(limit=args.limit)
    payload = {
        "lock_acquired": result.lock_acquired,
        "breached_count": len(result.items),
        "command_ids": [row.command.command_id for row in result.items],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
