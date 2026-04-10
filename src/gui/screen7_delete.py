import threading

import customtkinter as ctk

from src.utils.disk_utils import human_size


class Screen7Delete(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._build_ui()

    def _build_ui(self):
        assets = self.app.selected_assets
        photos = sum(1 for a in assets if a.media_type in ("photo", "live_photo_image"))
        videos = sum(1 for a in assets if a.media_type in ("video", "live_photo_video"))
        total_bytes = sum(a.file_size for a in assets)

        ctk.CTkLabel(
            self, text="Free Up iPhone Space",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(50, 8))

        # Warning box
        warning_frame = ctk.CTkFrame(self, fg_color="#4a1010", corner_radius=10)
        warning_frame.pack(padx=80, pady=12, fill="x")
        ctk.CTkLabel(
            warning_frame,
            text=(
                f"You are about to permanently delete {photos:,} photos "
                f"and {videos:,} videos\n"
                f"({human_size(total_bytes)}) from your iPhone.\n\n"
                f"This cannot be undone."
            ),
            font=ctk.CTkFont(size=13), text_color="#FF6B6B", wraplength=600
        ).pack(pady=16, padx=20)

        # Confirmation checkbox
        self.confirm_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self,
            text="I understand this will permanently delete these files from my iPhone",
            variable=self.confirm_var,
            command=self._on_checkbox,
            font=ctk.CTkFont(size=12),
        ).pack(pady=16)

        # Delete button (disabled until checkbox checked)
        self.delete_btn = ctk.CTkButton(
            self,
            text="Delete from iPhone", width=240, height=44,
            fg_color="#D32F2F", hover_color="#B71C1C",
            command=self._start_deletion,
            state="disabled",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.delete_btn.pack(pady=8)

        # Cancel button
        ctk.CTkButton(
            self, text="Cancel — Keep Files on iPhone", width=240,
            fg_color="gray30",
            command=lambda: self.app.show_screen("connect")
        ).pack(pady=8)

        # Progress bar (shown during deletion)
        self.progress_bar = ctk.CTkProgressBar(self, width=600)
        self.progress_bar.pack(pady=16)
        self.progress_bar.set(0)

        # Status label
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=4)

    def _on_checkbox(self):
        self.delete_btn.configure(
            state="normal" if self.confirm_var.get() else "disabled"
        )

    def _start_deletion(self):
        # Disable the button to prevent double-clicks
        self.delete_btn.configure(state="disabled")
        self.confirm_var.set(False)
        thread = threading.Thread(target=self._run_deletion, daemon=True)
        thread.start()

    def _run_deletion(self):
        assets = self.app.selected_assets
        device = self.app.device
        dest = self.app.destination
        deleted = 0
        failed = 0

        for i, asset in enumerate(assets):
            # Pre-verify: destination copy must exist and size must match
            dest_path = (
                dest
                / str(asset.date_taken.year)
                / asset.date_taken.strftime("%B")
                / asset.filename
            )
            if not dest_path.exists() or dest_path.stat().st_size != asset.file_size:
                failed += 1
                self.after(0, lambda f=asset.filename: self.status_label.configure(
                    text=f"Skipping {f} — destination copy not verified",
                    text_color="#FF9800"
                ))
                continue

            try:
                device.delete_file(asset)
                deleted += 1
            except Exception:
                failed += 1

            pct = (i + 1) / len(assets)
            self.after(0, self.progress_bar.set, pct)
            self.after(0, lambda d=deleted, t=len(assets): self.status_label.configure(
                text=f"Deleting… {d} of {t} files",
                text_color="white"
            ))

        total_freed = sum(a.file_size for a in assets)
        self.after(0, self._on_done, deleted, failed, total_freed)

    def _on_done(self, deleted: int, failed: int, freed_bytes: int):
        if not self.winfo_exists():
            return
        self.status_label.configure(
            text=(
                f"Done. Space Freed: {human_size(freed_bytes)}. "
                f"({deleted} deleted, {failed} skipped)"
            ),
            text_color="#4CAF50"
        )
        self.after(4000, lambda: self.app.show_screen("connect"))
