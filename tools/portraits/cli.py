from __future__ import annotations

import argparse
from pathlib import Path

from .server import run_workbench_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.portraits", description="Portrait Workbench developer server")
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("workbench-server", help="start the Portrait Workbench API")
    server.add_argument("--input", default="portrait-library", help="file-backed workspace directory")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.set_defaults(func=lambda args: run_workbench_server(args.host, args.port, Path(args.input)) or 0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
