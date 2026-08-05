from __future__ import annotations

import argparse
from pathlib import Path

from tools.cards.style_pipeline import StyleStore

from .production import CardProductionManager
from .server import run_workbench_server
from .workspace import WorkspaceStore


def cleanup_workspace(path: Path) -> int:
    store = WorkspaceStore(path)
    styles = StyleStore(store)
    styles.ensure_initial()
    manager = CardProductionManager(store, styles)
    removed_batches = manager.remove_simulation_batches()
    protected = {str(batch.get("style_version_id")) for batch in manager.list()}
    removed_versions = styles.remove_simulation_versions()
    removed_versions.extend(styles.remove_superseded_legacy_versions(protected))
    print(f"Removed {len(removed_batches)} simulation batches and {len(removed_versions)} superseded pipeline versions from {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.portraits", description="Portrait Workbench developer server")
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("workbench-server", help="start the Portrait Workbench API")
    server.add_argument("--input", default="portrait-library", help="file-backed workspace directory")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.set_defaults(func=lambda args: run_workbench_server(args.host, args.port, Path(args.input)) or 0)
    cleanup = sub.add_parser("cleanup-workspace", help="remove superseded simulation data after seeding the two real pipelines")
    cleanup.add_argument("--input", default="portrait-library", help="file-backed workspace directory")
    cleanup.set_defaults(func=lambda args: cleanup_workspace(Path(args.input)))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
