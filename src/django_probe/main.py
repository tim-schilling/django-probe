"""Commands used by Django Probe CI jobs and local inspection workflows."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path

from django_probe.config import resolve_token
from django_probe.init import init
from django_probe.login import login
from django_probe.logout import logout
from django_probe.payload import build_payload
from django_probe.submit import SubmitError, submit

DEFAULT_SERVER = "https://djangoprobe.org"
#: Plain HTTP to one of these is a local development server, not a network hop.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def insecure_server_url(server_url: str) -> str | None:
    """Return a message explaining why `server_url` is unsafe, or None if it isn't.

    Everything the CLI sends a server carries a credential in a header - a project
    token for `submit`, the personal one for `login` and `init` - so plain HTTP puts
    it in front of anyone on the path.
    """
    parsed = urllib.parse.urlparse(server_url)
    if parsed.scheme == "https":
        return None
    if parsed.scheme != "http":
        return f"unsupported scheme in {server_url!r}: expected http:// or https://."
    if parsed.hostname in LOOPBACK_HOSTS:
        return None
    return (
        f"refusing to send a credential to {server_url} over plain HTTP, where "
        "anyone on the network path can read it. Use an https:// URL, or pass "
        "--allow-insecure-http to override."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="django-probe",
        description=(
            "Share aggregate Django API usage from CI, or inspect the payload "
            "locally. Source code, file paths and repository names are never sent."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("path", nargs="?", default=".", help="Project root to scan.")

    def add_server(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--server-url",
            default=os.environ.get("DJANGO_PROBE_SERVER", DEFAULT_SERVER),
        )
        p.add_argument(
            "--allow-insecure-http",
            action="store_true",
            help="Permit a plain-HTTP server URL. Sends your credential in the clear.",
        )

    scan = sub.add_parser(
        "scan", help="Print the payload as JSON without sending anything."
    )
    add_common(scan)

    send = sub.add_parser("submit", help="Scan, then send the payload to a server.")
    add_common(send)
    add_server(send)
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload instead of sending it.",
    )

    login_parser = sub.add_parser(
        "login", help="Authenticate this machine via your browser."
    )
    add_server(login_parser)
    login_parser.add_argument(
        "--org",
        dest="org_slug",
        help="Organization slug to log in for (see the organization's page).",
    )

    init_parser = sub.add_parser(
        "init",
        help="Create a project using your stored login and print its token.",
    )
    add_common(init_parser)
    add_server(init_parser)
    init_parser.add_argument(
        "--org",
        dest="org_slug",
        help="Must match the org you're logged in for; a safety check, not a selector.",
    )
    init_parser.add_argument(
        "--name", help="Project name (defaults to the directory name)."
    )

    sub.add_parser(
        "logout", help="Revoke and forget the locally stored login credential."
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # `scan` takes no server, and `submit --dry-run` prints the payload instead of
    # sending it, so neither puts a credential on the wire.
    contacts_server = args.command in {"submit", "login", "init"} and not getattr(
        args, "dry_run", False
    )
    if contacts_server:
        problem = insecure_server_url(args.server_url)
        if problem is not None and not args.allow_insecure_http:
            print(problem, file=sys.stderr)
            return 2

    if args.command == "login":
        return login(args.server_url, args.org_slug, socket.gethostname())

    if args.command == "logout":
        return logout()

    root = Path(args.path).resolve()

    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    if args.command == "init":
        return init(root, args.server_url, args.org_slug, args.name)

    payload = build_payload(root)

    if args.command == "scan" or args.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    try:
        response = submit(payload, args.server_url, token=resolve_token(root))
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
