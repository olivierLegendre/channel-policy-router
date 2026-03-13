import argparse
import json

from channel_policy_router.main import create_use_cases
from channel_policy_router.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Deliver incident hooks in batch")
    parser.add_argument("--limit", type=int, default=100, help="Max events to process")
    args = parser.parse_args()

    use_cases = create_use_cases(Settings())
    result = use_cases.deliver_incident_hooks_batch(limit=args.limit)
    payload = {
        "lock_acquired": result.lock_acquired,
        "delivered_count": result.delivered_count,
        "failed_count": result.failed_count,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
