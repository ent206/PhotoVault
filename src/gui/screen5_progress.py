import threading
from typing import Optional

import customtkinter as ctk

from src.transfer_engine import TransferEngine, TransferProgress
from src.utils.disk_utils import human_size


class Screen5Progress(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._engine: Optional[TransferEngine] = None
        self._paused = False
        self._cancelled = False
        self._build_ui()
        self._start_transfer()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Transferring…",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(50, 8))

        # Current file being copied
        self.file_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="gray60"
        )
        self.file_label.pack(pady=4)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self, width=700, height=16)
        self.progress_bar.pack(pady=16)
        self.progress_bar.set(0)

        # Stats frame
        stats_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=10)
        stats_frame.pack(padx=80, pady=8, fill="x")

        self.count_label = ctk.CTkLabel(
            stats_frame, text="0 of 0 files",
            font=ctk.CTkFont(size=14)
        )
        self.count_label.pack(pady=(12, 4))

        self.size_label = ctk.CTkLabel(
            stats_frame, text="0 B of 0 B",
            font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.size_label.pack(pady=4)

        self.speed_label = ctk.CTkLabel(
            stats_frame, text="",
            font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.speed_label.pack(pady=(4, 12))

        # ETA
        self.eta_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.eta_label.pack(pady=4)

        # Sleep warning banner (hidden by default)
        self.sleep_banner = ctk.CTkFrame(self, fg_color="#7a4400", corner_radius=8)
        self.sleep_label = ctk.CTkLabel(
            self.sleep_banner,
            text="⚠ Connection hiccup — retrying…",
            font=ctk.CTkFont(size=12), text_color="#FFB74D"
        )
        self.sleep_label.pack(pady=10, padx=16)

        # Pause and Cancel buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=24)
        self._btn_frame = btn_frame

        self.pause_btn = ctk.CTkButton(
            btn_frame, text="Pause", width=140,
            command=self._toggle_pause
        )
        self.pause_btn.pack(side="left", padx=12)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=140,
            command=self._cancel, fg_color="gray40"
        ).pack(side="left", padx=12)

    def _start_transfer(self):
        """Create transfer engine and start it in a background thread."""
        # Set session_id for resume BEFORE constructing engine
        if self.app.resume_session:
            self.app.transfer_options.session_id = self.app.resume_session.session_id

        self._engine = TransferEngine(
            device=self.app.device,
            destination=self.app.destination,
            session_log=self.app.session_log,
            options=self.app.transfer_options,
            on_progress=self._on_progress,
            on_device_sleeping=self._on_device_sleeping,
            on_device_resumed=self._on_device_resumed,
        )
        thread = threading.Thread(target=self._run_transfer, daemon=True)
        thread.start()

    def _run_transfer(self):
        try:
            results = self._engine.transfer(self.app.selected_assets)
            self.after(0, self._on_complete, results)
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_progress(self, p: TransferProgress):
        """Called from the transfer thread — must use self.after() to update UI."""
        self.after(0, self._update_ui, p)

    def _update_ui(self, p: TransferProgress):
        if not self.winfo_exists():
            return
        self.file_label.configure(text=p.current_filename)
        pct = p.files_done / p.files_total if p.files_total else 0
        self.progress_bar.set(pct)
        self.count_label.configure(
            text=f"{p.files_done:,} of {p.files_total:,} files"
        )
        if p.bytes_total > 0:
            self.size_label.configure(
                text=f"{human_size(p.bytes_done)} of {human_size(p.bytes_total)}"
            )
        elif p.bytes_done > 0:
            self.size_label.configure(text=f"{human_size(p.bytes_done)} transferred")
        if p.speed_mbps > 0:
            self.speed_label.configure(text=f"{p.speed_mbps:.1f} MB/s")
        if p.eta_seconds > 0:
            m, s = divmod(int(p.eta_seconds), 60)
            self.eta_label.configure(text=f"About {m}m {s}s remaining")

    def _toggle_pause(self):
        if not self._paused:
            self._engine.pause()
            self.pause_btn.configure(text="Resume")
            self._paused = True
        else:
            self._engine.resume_pause()
            self.pause_btn.configure(text="Pause")
            self._paused = False

    def _cancel(self):
        self._cancelled = True
        if self._engine:
            self._engine.cancel()
        self.after(500, lambda: self.app.show_screen("connect"))

    def _on_complete(self, results: dict):
        if self._cancelled:
            return
        self.app.transfer_results = results
        self.app.show_screen("complete")

    def _on_device_sleeping(self, retry_in: int):
        self.after(0, self._show_sleep_banner, retry_in)

    def _on_device_resumed(self):
        self.after(0, self._hide_sleep_banner)

    def _show_sleep_banner(self, retry_in: int):
        if not self.winfo_exists():
            return
        self.sleep_label.configure(
            text=f"⚠ Connection hiccup — retrying in {retry_in}s…"
        )
        self.sleep_banner.pack(before=self._btn_frame, padx=80, pady=(0, 8), fill="x")

    def _hide_sleep_banner(self):
        if not self.winfo_exists():
            return
        self.sleep_banner.pack_forget()

    def _on_error(self, msg: str):
        if not self.winfo_exists():
            return
        self.file_label.configure(text=f"Error: {msg}", text_color="#F44336")
        self.pause_btn.configure(state="disabled")
        # Show error but don't navigate — let user read the message and cancel manually
