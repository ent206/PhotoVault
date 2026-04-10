#!/usr/bin/env python3
# main.py
import argparse
import sys
from pathlib import Path

import customtkinter as ctk

from src.config import get_last_destination
from src.session_log import SessionLog
from src.gui.app import PhotoVaultApp


def main():
    parser = argparse.ArgumentParser(description="PhotoVault — iPhone photo transfer")
    parser.add_argument(
        "--mock",
        metavar="PATH",
        nargs="?",
        const="./mock_library",
        help="Use mock device from PATH (default: ./mock_library)",
    )
    args = parser.parse_args()

    # Clean up partial files from any previous crash
    last_dest = get_last_destination()
    if last_dest and Path(last_dest).exists():
        from src.transfer_engine import TransferEngine
        cleaned = TransferEngine.cleanup_partials(Path(last_dest))
        if cleaned:
            print(f"Cleaned up {cleaned} partial file(s) from previous session.")

    # Check for incomplete sessions
    log = SessionLog()
    incomplete = log.find_incomplete()

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = PhotoVaultApp(
        mock_path=Path(args.mock) if args.mock else None,
        incomplete_sessions=incomplete,
        session_log=log,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
