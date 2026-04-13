#!/usr/bin/env python3
# main.py
import argparse
from pathlib import Path

import webview

from src.config import get_last_destination
from src.session_log import SessionLog
from api import PhotoVaultAPI


def main():
    parser = argparse.ArgumentParser(description="PhotoVault — iPhone photo transfer")
    parser.add_argument(
        "--mock",
        metavar="PATH",
        nargs="?",
        const="./mock_library",
        help="Use mock device from PATH (default: ./mock_library)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Load React from Vite dev server (localhost:5173)",
    )
    args = parser.parse_args()

    # Clean up partial files from any previous crash
    last_dest = get_last_destination()
    if last_dest:
        try:
            dest_path = Path(last_dest)
            if dest_path.exists() and dest_path.is_dir():
                from src.transfer_engine import TransferEngine
                cleaned = TransferEngine.cleanup_partials(dest_path)
                if cleaned:
                    print(f"Cleaned up {cleaned} partial file(s) from previous session.")
        except OSError:
            pass

    session_log = SessionLog()

    api = PhotoVaultAPI(
        session_log=session_log,
        mock_path=Path(args.mock) if args.mock else None,
    )

    if args.dev:
        url = "http://localhost:5173"
    else:
        dist = Path(__file__).parent / "frontend" / "dist" / "index.html"
        url = dist.resolve().as_uri()

    window = webview.create_window(
        title="PhotoVault",
        url=url,
        js_api=api,
        width=960,
        height=820,
        min_size=(800, 600),
        resizable=True,
        text_select=False,
        confirm_close=False,
    )

    api.set_window(window)

    # debug=True enables the WebKit inspector
    webview.start(debug=args.dev)


if __name__ == "__main__":
    main()
