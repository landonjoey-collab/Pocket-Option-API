"""CLI entry point: python -m kalshi_copier --config kalshi_config.json"""

import argparse
import asyncio
import sys

from kalshi_copier.config import load_config
from kalshi_copier.copier import KalshiCopier


def main():
    parser = argparse.ArgumentParser(
        prog="kalshi_copier",
        description="Kalshi trade copier: mirror one master account's fills "
                    "to any number of follower accounts.",
    )
    parser.add_argument("--config", default="kalshi_config.json",
                        help="path to the JSON config (default: kalshi_config.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="watch the master fill stream and log what would "
                             "be copied, without placing any orders")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        print("hint: copy kalshi_copier/config.example.json to "
              "kalshi_config.json and fill in your API keys", file=sys.stderr)
        sys.exit(1)

    copier = KalshiCopier(config, dry_run=args.dry_run)
    try:
        asyncio.run(copier.run())
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
