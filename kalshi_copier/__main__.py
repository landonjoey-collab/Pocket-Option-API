"""CLI entry point: python -m kalshi_copier --config kalshi_config.json"""

import argparse
import asyncio
import os
import sys

from kalshi_copier.config import load_config
from kalshi_copier.copier import HALT_FILE, KalshiCopier, halt_reason


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
    parser.add_argument("--halt", action="store_true",
                        help="emergency stop: create the KALSHI_HALT kill-switch "
                             "file and exit; a copier running in this directory "
                             "stops copying within a second")
    parser.add_argument("--resume", action="store_true",
                        help="remove the KALSHI_HALT kill-switch file so the "
                             "copier can be started again")
    args = parser.parse_args()

    if args.halt:
        with open(HALT_FILE, "w", encoding="utf-8") as fh:
            fh.write("Kalshi trading halted. Delete this file "
                     "(or run `python -m kalshi_copier --resume`) to allow trading.\n")
        print(f"halted: created {os.path.abspath(HALT_FILE)} — "
              "no orders will be placed until it is removed")
        return
    if args.resume:
        if os.path.exists(HALT_FILE):
            os.remove(HALT_FILE)
            print(f"resumed: removed {os.path.abspath(HALT_FILE)}")
        else:
            print(f"no {HALT_FILE} file here")
        remaining = halt_reason()
        if remaining:
            print(f"still halted: {remaining}")
        return

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
