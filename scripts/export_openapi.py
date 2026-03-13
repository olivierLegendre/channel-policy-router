import json
import os
from pathlib import Path


def _configure_env() -> None:
    os.environ.setdefault("CHANNEL_POLICY_ROUTER_PERSISTENCE_BACKEND", "in_memory")
    os.environ.setdefault("CHANNEL_POLICY_ROUTER_POSTGRES_AUTO_INIT", "false")


def main() -> None:
    _configure_env()
    from channel_policy_router.main import create_app

    app = create_app()
    schema = app.openapi()
    output = Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
