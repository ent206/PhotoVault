# src/gui/app.py
from pathlib import Path
from typing import List, Optional

import customtkinter as ctk

from src.models import TransferSession
from src.session_log import SessionLog


class PhotoVaultApp(ctk.CTk):
    def __init__(
        self,
        mock_path: Optional[Path],
        incomplete_sessions: List[TransferSession],
        session_log: SessionLog,
    ):
        super().__init__()
        self.title("PhotoVault")
        self.geometry("900x650")
        self.resizable(False, False)

        # Shared state passed between screens
        self.mock_path = mock_path
        self.session_log = session_log
        self.device = None           # Set by Screen 1
        self.destination = None      # Set by Screen 2 (Path)
        self.selected_assets = []    # Set by Screen 3
        self.transfer_options = None # Set by Screen 4
        self.transfer_results = None # Set by Screen 5
        self.resume_session = None   # Set if resuming

        self._current_screen = None

        if incomplete_sessions:
            self._show_resume_prompt(incomplete_sessions[0])
        else:
            self.show_screen("connect")

    def show_screen(self, name: str, **kwargs) -> None:
        if self._current_screen:
            self._current_screen.destroy()

        screen_map = {
            "connect": "src.gui.screen1_connect.Screen1Connect",
            "destination": "src.gui.screen2_destination.Screen2Destination",
            "dates": "src.gui.screen3_dates.Screen3Dates",
            "summary": "src.gui.screen4_summary.Screen4Summary",
            "progress": "src.gui.screen5_progress.Screen5Progress",
            "complete": "src.gui.screen6_complete.Screen6Complete",
            "delete": "src.gui.screen7_delete.Screen7Delete",
        }
        module_path, class_name = screen_map[name].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        self._current_screen = cls(self, **kwargs)
        self._current_screen.pack(fill="both", expand=True)

    def _show_resume_prompt(self, session: TransferSession) -> None:
        """Show Screen 1 in background and a resume dialog on top."""
        self.show_screen("connect")

        dialog = ctk.CTkToplevel(self)
        dialog.title("Resume Transfer?")
        dialog.geometry("480x260")
        dialog.grab_set()
        dialog.lift()

        started = session.started_at.strftime("%b %d, %Y at %I:%M %p")
        done = session.completed_count
        total = session.total_files

        ctk.CTkLabel(
            dialog, text="Incomplete Transfer Found",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(24, 8))
        ctk.CTkLabel(
            dialog,
            text=f"Started: {started}\n{done} of {total} files completed",
            font=ctk.CTkFont(size=13),
        ).pack(pady=8)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=16)

        def on_resume():
            dialog.destroy()
            self.destination = Path(session.destination_path)
            self.resume_session = session
            self.show_screen("connect", resume_session=session)

        def on_start_fresh():
            dialog.destroy()
            self.show_screen("connect")

        ctk.CTkButton(
            btn_frame, text="Resume Transfer", command=on_resume, width=180
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_frame, text="Start Fresh", command=on_start_fresh,
            fg_color="gray40", width=180
        ).pack(side="left", padx=8)
