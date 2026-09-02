"""django-probe command line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from django_probe.payload import build_payload
from django_probe.submit import SubmitError, submit

DEFAULT_SERVER = "https://djangoprobe.org"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="django-probe",
        description=(
            "Count how often a Django project uses particular APIs. Only counts are "
            "reported. Source code, file paths and repository names are never sent."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("path", nargs="?", default=".", help="Project root to scan.")

    scan = sub.add_parser(
        "scan", help="Print the payload as JSON without sending anything."
    )
    add_common(scan)

    send = sub.add_parser("submit", help="Scan, then send the payload to a server.")
    add_common(send)
    send.add_argument(
        "--server-url", default=os.environ.get("DJANGO_PROBE_SERVER", DEFAULT_SERVER)
    )
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload instead of sending it.",
    )

    sub.add_parser("init", help="Print a random project key.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init":
        print(uuid.uuid4())
        return 0

    root = Path(args.path).resolve()

    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    payload = build_payload(root)

    if args.command == "scan" or args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    try:
        response = submit(payload, args.server_url)
    except SubmitError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    total = sum(payload["patterns"].values())
    print(
        f"Submitted {total} pattern occurrences across "
        f"{payload['files_scanned']} files. ({response.get('status', 'ok')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
