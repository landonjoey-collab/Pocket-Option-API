"""CLI entry point: python -m trade_copier --config copier_config.json"""

import argparse
import asyncio
import sys

from trade_copier.config import load_config
from trade_copier.copier import TradeCopier


def main():
    parser = argparse.ArgumentParser(
        prog="trade_copier",
        description="Pocket Option trade copier: mirror one master account's "
                    "trades to any number of follower accounts.",
    )
    parser.add_argument("--config", default="copier_config.json",
                        help="path to the JSON config (default: copier_config.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="watch the master and log what would be copied, "
                             "without connecting followers or placing orders")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        print("hint: copy trade_copier/config.example.json to "
              "copier_config.json and fill in your SSIDs", file=sys.stderr)
        sys.exit(1)

    copier = TradeCopier(config, dry_run=args.dry_run)
    try:
        asyncio.run(copier.run())
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
