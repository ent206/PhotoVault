import uuid
from pathlib import Path

import customtkinter as ctk

from src.transfer_engine import TransferOptions
from src.utils.disk_utils import human_size


class Screen4Summary(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._build_ui()

    def _build_ui(self):
        assets = self.app.selected_assets
        dest = self.app.destination

        photos = sum(1 for a in assets if a.media_type in ("photo", "live_photo_image"))
        videos = sum(1 for a in assets if a.media_type in ("video", "live_photo_video"))
        total_bytes = sum(a.file_size for a in assets)
        stubs = sum(1 for a in assets if a.is_icloud_stub)

        # Duplicate detection: check destination for files with same name + size
        duplicates = sum(
            1 for a in assets
            if _dest_path(dest, a).exists()
            and _dest_path(dest, a).stat().st_size == a.file_size
        )

        # ETA at USB 2.0 baseline: ~35 MB/s
        eta_seconds = (total_bytes / 1_048_576) / 35 if total_bytes else 0
        eta_str = _format_eta(eta_seconds)

        ctk.CTkLabel(
            self, text="Ready to Transfer",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(40, 4))

        # Info table
        info_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=12)
        info_frame.pack(padx=80, pady=16, fill="x")

        rows = [
            ("Photos", f"{photos:,}"),
            ("Videos", f"{videos:,}"),
            ("Total Size", human_size(total_bytes)),
            ("Destination", str(dest)),
            ("Estimated Time", eta_str),
            ("Already Copied (will skip)", f"{duplicates:,}"),
        ]
        if stubs:
            rows.append((
                "iCloud Placeholders ⚠",
                f"{stubs:,} — originals not on device"
            ))

        for label, value in rows:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=12),
                text_color="gray60", width=220, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=ctk.CTkFont(size=13), anchor="w"
            ).pack(side="left")

        # Safe Mode toggle
        self.safe_mode_var = ctk.BooleanVar(value=True)
        safe_frame = ctk.CTkFrame(self, fg_color="gray20", corner_radius=10)
        safe_frame.pack(padx=80, pady=8, fill="x")
        ctk.CTkSwitch(
            safe_frame, text="Safe Mode (MD5 Verification)",
            variable=self.safe_mode_var,
            font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=16, pady=12)
        ctk.CTkLabel(
            safe_frame,
            text="Confirms every file copied correctly, bit for bit. Slightly slower.",
            font=ctk.CTkFont(size=11), text_color="gray60"
        ).pack(side="left", padx=8)

        # Start Transfer button
        ctk.CTkButton(
            self, text="Start Transfer", width=220, height=44,
            command=self._start,
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=24)

    def _start(self):
        self.app.transfer_options = TransferOptions(
            safe_mode=self.safe_mode_var.get(),
            session_id=str(uuid.uuid4()),
        )
        self.app.show_screen("progress")


def _dest_path(dest: Path, asset) -> Path:
    """Compute destination path for duplicate detection (Year/Month/filename)."""
    month_name = asset.date_taken.strftime("%B")
    year = str(asset.date_taken.year)
    return dest / year / month_name / asset.filename


def _format_eta(seconds: float) -> str:
    """Format seconds as human-readable ETA string."""
    if seconds <= 0:
        return "Instant"
    if seconds < 60:
        return f"{seconds:.0f} seconds"
    if seconds < 3600:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"
