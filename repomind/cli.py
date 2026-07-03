"""CLI entry point for RepoMind."""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="repomind",
        description="RepoMind — AI-powered deep codebase understanding",
    )
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Start the web UI (default)")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8420)
    serve_p.add_argument("--no-browser", action="store_true")

    analyze_p = sub.add_parser("analyze", help="Analyze a repository")
    analyze_p.add_argument("repo_path")
    analyze_p.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")

    summary_p = sub.add_parser("summary", help="Print repo summary")
    summary_p.add_argument("repo_path")
    summary_p.add_argument("--level", choices=["project", "directory", "file"], default="project")
    summary_p.add_argument("--path", default="")

    args = parser.parse_args()

    if args.command is None or args.command == "serve":
        _serve(args)
    elif args.command == "analyze":
        _analyze(args)
    elif args.command == "summary":
        _summary(args)


def _serve(args):
    import threading
    import time
    import webbrowser

    import uvicorn

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8420)

    if not getattr(args, "no_browser", False):
        def _open():
            time.sleep(1)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run("repomind.main:app", host=host, port=port, reload=False)


def _analyze(args):
    import asyncio
    from pathlib import Path

    from .config import load_settings
    from .understanding.analyzer import analyze_repo

    repo = Path(args.repo_path).expanduser().resolve()
    if not repo.is_dir():
        print(f"Error: {repo} is not a directory", file=sys.stderr)
        sys.exit(1)

    settings = load_settings(repo)
    print(f"Analyzing {repo} (depth={args.depth})...")
    result = asyncio.run(analyze_repo(repo, settings, depth=args.depth))

    if result.state == "error":
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    print(f"Done! {result.files_done} files, {result.directories_done} directories analyzed.")


def _summary(args):
    from pathlib import Path

    from .understanding.knowledge_base import KnowledgeBase

    repo = Path(args.repo_path).expanduser().resolve()
    kb = KnowledgeBase.load(repo)

    if args.level == "project":
        ov = kb.get_project_overview()
        if not ov:
            print("No analysis found. Run 'repomind analyze <path>' first.")
            sys.exit(1)
        print(f"\n{'='*60}")
        print(f"Project: {ov.get('name', '?')}")
        print(f"{'='*60}")
        print(ov.get("summary", ""))
        if ov.get("tech_stack"):
            print(f"\nTech: {', '.join(ov['tech_stack'])}")
        if ov.get("architecture"):
            print(f"Architecture: {ov['architecture']}")
    elif args.level == "directory":
        s = kb.get_directory_summary(args.path)
        if s:
            print(f"\n{args.path}:\n{s.get('summary', '')}")
        else:
            print(f"No summary for: {args.path}")
    elif args.level == "file":
        s = kb.get_file_summary(args.path)
        if s:
            print(f"\n{args.path}:\n{s.get('summary', '')}")
        else:
            print(f"No summary for: {args.path}")


if __name__ == "__main__":
    main()
