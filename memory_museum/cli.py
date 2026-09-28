"""Command line interface: ``python -m memory_museum <command>``."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import webbrowser
from pathlib import Path

from memory_museum import __version__
from memory_museum.config import DEMO_DATA_DIR, FRONTEND_DIST, Paths, resolve_paths
from memory_museum.db import open_db


def _print(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:  # legacy Windows consoles
        print(msg.encode(sys.stdout.encoding or "ascii", "replace").decode(sys.stdout.encoding or "ascii"), flush=True)


def _paths(args) -> Paths:
    return resolve_paths(getattr(args, "data_dir", None)).ensure()


def cmd_init(args) -> int:
    paths = _paths(args)
    open_db(paths.db).close()
    private = Path("private-data")
    for sub in ("chat", "media"):
        (private / sub).mkdir(parents=True, exist_ok=True)
    _print(f"Data directory ready: {paths.root}")
    _print(f"Put your exports into: {private.resolve()}{Path('/chat').as_posix()} and .../media")
    _print("Both folders are ignored by git. Next: python -m memory_museum import --chat private-data/chat "
           "--media private-data/media")
    return 0


def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes", "是", "确认")


def cmd_import(args) -> int:
    from memory_museum.pipeline import commit_staging, discard_staging, format_preview, open_staging, run_import

    paths = _paths(args)
    chat = [Path(p) for p in (args.chat or [])]
    media = [Path(p) for p in (args.media or [])]
    for p in chat + media:
        if not p.exists():
            _print(f"error: input not found: {p}")
            return 2
    if not chat and not media:
        _print("error: give --chat and/or --media")
        return 2

    staging = open_staging(paths)
    try:
        result = run_import(staging, paths, chat_inputs=chat, media_inputs=media, parser=args.parser,
                            conversation=args.conversation, timezone=getattr(args, "timezone", None), log=_print)
    except ValueError as e:
        staging.close()
        discard_staging(paths)
        _print(f"error: {e}")
        return 2
    finally:
        staging.close()
    _print(format_preview(result))
    if args.report:
        Path(args.report).write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        _print(f"Full report written to {args.report}")

    if args.dry_run:
        discard_staging(paths)
        _print("Dry run: nothing was saved.")
        return 0
    if args.yes or _confirm("Save this import into the museum? [y/N] "):
        commit_staging(paths)
        _print("Import saved. Start the museum with: python -m memory_museum serve")
        return 0
    discard_staging(paths)
    _print("Import discarded; the museum was not changed. Fix the inputs and run the import again "
           "(use --yes to skip this question).")
    return 1


def cmd_import_chat(args) -> int:
    args.chat, args.media = args.input, []
    return cmd_import(args)


def cmd_import_media(args) -> int:
    args.chat, args.media = [], args.input
    args.parser = args.conversation = args.timezone = None
    return cmd_import(args)


def cmd_build_index(args) -> int:
    from memory_museum.association import associate
    from memory_museum.index import build_index

    paths = _paths(args)
    conn = open_db(paths.db)
    try:
        _print("Linking media to messages ...")
        rep = associate(conn)
        _print(f"  exact {rep.exact}, high {rep.high}, medium {rep.medium}, low suggestions {rep.low_suggestions}")
        _print("Building day index and statistics ...")
        _print(f"  {build_index(conn)['days']} days indexed")
    finally:
        conn.close()
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from memory_museum.api.app import create_app

    paths = _paths(args)
    if not (FRONTEND_DIST / "index.html").exists():
        _print("warning: frontend not built. Run:  cd frontend && npm install && npm run build")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        _print("")
        _print(f"WARNING: listening on {args.host} makes the museum reachable by other devices on your network.")
        _print("         Set a PIN first (python -m memory_museum set-pin) and only do this on a network you trust.")
        _print("")
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}/"
    _print(f"Our Memory Museum is running at {url}  (Ctrl+C to stop)")
    _print(f"Data: {paths.root}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(create_app(paths), host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_demo(args) -> int:
    from memory_museum.pipeline import commit_staging, format_preview, open_staging, run_import

    if not args.data_dir:
        args.data_dir = str(Path("data") / "demo")
    paths = _paths(args)
    if args.reset:
        _purge(paths)
        paths.ensure()
    if not paths.db.exists() or args.reset:
        chat, media = DEMO_DATA_DIR / "chat", DEMO_DATA_DIR / "media"
        if not chat.exists():
            _print(f"error: demo data missing at {DEMO_DATA_DIR}. Run: python -m memory_museum generate-demo")
            return 2
        _print("Importing the fictional demo couple into data/demo ...")
        staging = open_staging(paths)
        try:
            result = run_import(staging, paths, chat_inputs=[chat], media_inputs=[media], log=_print)
        finally:
            staging.close()
        _print(format_preview(result))
        commit_staging(paths)
    if args.no_serve:
        return 0
    return cmd_serve(args)


def cmd_generate_demo(args) -> int:
    from memory_museum import demo_gen

    if args.stress:
        out = Path(args.out or "demo-data-stress")
        demo_gen.generate_stress(out, messages=args.messages, photos=args.photos, voices=args.voices, seed=args.seed)
    else:
        out = Path(args.out or DEMO_DATA_DIR)
        demo_gen.generate_demo(out, seed=args.seed)
    _print(f"Synthetic data written to {out.resolve()}")
    return 0


def cmd_set_pin(args) -> int:
    import getpass

    from memory_museum import security

    paths = _paths(args)
    conn = open_db(paths.db)
    try:
        pin = args.pin or getpass.getpass("New PIN/password (4-64 chars): ")
        if not args.pin and getpass.getpass("Repeat: ") != pin:
            _print("PINs do not match.")
            return 1
        security.set_pin(conn, pin)
    except ValueError as e:
        _print(f"error: {e}")
        return 1
    finally:
        conn.close()
    _print("PIN set. Restart the server if it is running. Remember: this is an access lock, not encryption.")
    return 0


def cmd_clear_pin(args) -> int:
    from memory_museum import security

    conn = open_db(_paths(args).db)
    security.set_pin(conn, None)
    conn.close()
    _print("PIN removed. Restart the server if it is running.")
    return 0


def _purge(paths: Paths) -> list[str]:
    removed = []
    for p in (paths.db, paths.staging_db):
        for suffix in ("", "-wal", "-shm", "-journal"):
            f = Path(str(p) + suffix)
            if f.exists():
                f.unlink()
                removed.append(str(f))
    for d in (paths.cache, paths.avatars):
        if d.exists():
            shutil.rmtree(d)
            removed.append(str(d) + "/")
    return removed


def cmd_purge(args) -> int:
    paths = resolve_paths(args.data_dir)
    _print(f"This deletes the museum database, thumbnails, avatars and caches in: {paths.root}")
    _print("Your original chat exports and media files are NOT touched.")
    if not (args.yes or _confirm("Delete all imported/derived data? [y/N] ")):
        _print("Nothing deleted.")
        return 1
    removed = _purge(paths)
    for r in removed:
        _print(f"  deleted {r}")
    _print("Done." if removed else "Nothing to delete.")
    return 0


def cmd_doctor(args) -> int:
    from memory_museum.media import ffmpeg
    from memory_museum.textstats import HAVE_JIEBA

    paths = resolve_paths(args.data_dir)
    caps = ffmpeg.capabilities()
    checks = [
        ("python", sys.version.split()[0], sys.version_info >= (3, 11)),
        ("data directory", str(paths.root), True),
        ("database", "present" if paths.db.exists() else "not created yet", True),
        ("frontend build", "ok" if (FRONTEND_DIST / "index.html").exists() else "missing (cd frontend; npm run build)",
         (FRONTEND_DIST / "index.html").exists()),
        ("ffmpeg", caps["ffmpeg"] or "not found (video thumbnails / durations disabled)", bool(caps["ffmpeg"])),
        ("ffprobe", caps["ffprobe"] or "not found (ffmpeg fallback used)", True),
        ("jieba (Chinese words)", "installed" if HAVE_JIEBA else "not installed (bigram fallback)", True),
    ]
    for name, value, ok in checks:
        _print(f"  [{'ok' if ok else '!!'}] {name}: {value}")
    return 0


def cmd_parsers(args) -> int:
    from memory_museum.parsers import PARSERS

    for p in PARSERS:
        _print(f"  {p.name:6} {', '.join(p.extensions):22} {p.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="memory_museum", description="Our Memory Museum — private, local-first.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--data-dir", help="where the database and caches live (default: ./data or $MEMORY_MUSEUM_DATA)")
        p.set_defaults(func=fn)
        return p

    add("init", cmd_init, "create the local data directory and private-data folders")

    def import_opts(p: argparse.ArgumentParser, with_parser: bool = True) -> None:
        if with_parser:
            p.add_argument("--parser", help="force a parser (see `parsers`); default: auto-detect per file")
            p.add_argument("--conversation", help="conversation id to assign to all imported messages")
            p.add_argument("--timezone", help="convert timestamps that carry a UTC offset into this zone "
                                              "(e.g. Asia/Shanghai, UTC+8); default: this computer's zone")
        p.add_argument("--yes", "-y", action="store_true", help="save without asking after the preview")
        p.add_argument("--dry-run", action="store_true", help="show the preview only; save nothing")
        p.add_argument("--report", help="write the full JSON import report to this file")

    p = add("import", cmd_import, "import chat exports and/or media folders (preview, then confirm)")
    p.add_argument("--chat", nargs="+", help="chat export files or folders")
    p.add_argument("--media", nargs="+", help="media folders or files")
    import_opts(p)

    p = add("import-chat", cmd_import_chat, "import chat exports only")
    p.add_argument("--input", nargs="+", required=True)
    import_opts(p)

    p = add("import-media", cmd_import_media, "scan media folders only")
    p.add_argument("--input", nargs="+", required=True)
    import_opts(p, with_parser=False)

    add("build-index", cmd_build_index, "re-run media linking and rebuild the day index/statistics")

    def serve_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1 (this computer only)")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--open", action="store_true", help="open the browser")

    serve_opts(add("serve", cmd_serve, "start the local museum web server"))
    p = add("demo", cmd_demo, "import the fictional demo dataset into data/demo and serve it")
    serve_opts(p)
    p.add_argument("--reset", action="store_true", help="re-import the demo data from scratch")
    p.add_argument("--no-serve", action="store_true", help="import only")

    p = add("generate-demo", cmd_generate_demo, "(re)generate synthetic demo data or a stress-test dataset")
    p.add_argument("--out")
    p.add_argument("--stress", action="store_true")
    p.add_argument("--messages", type=int, default=300_000)
    p.add_argument("--photos", type=int, default=10_000)
    p.add_argument("--voices", type=int, default=1_000)
    p.add_argument("--seed", type=int, default=20250301)

    p = add("set-pin", cmd_set_pin, "set or change the local PIN/password lock")
    p.add_argument("--pin", help=argparse.SUPPRESS)
    add("clear-pin", cmd_clear_pin, "remove the PIN lock")
    p = add("purge", cmd_purge, "delete the database, thumbnails and caches (never your original files)")
    p.add_argument("--yes", "-y", action="store_true")
    add("doctor", cmd_doctor, "check optional tools (ffmpeg, jieba, frontend build)")
    add("parsers", cmd_parsers, "list available chat parsers")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)
