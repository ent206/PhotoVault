from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from src import config
from src.utils.disk_utils import list_drives, human_size


class Screen2Destination(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._selected_path: Optional[Path] = None

        self._build_ui()
        self._load_drives()
        self._restore_last()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Choose Destination",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(40, 4))
        ctk.CTkLabel(
            self, text="Where should your photos be saved?",
            font=ctk.CTkFont(size=13), text_color="gray60"
        ).pack(pady=(0, 24))

        # Drive list label
        ctk.CTkLabel(
            self, text="Connected Drives",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="gray50"
        ).pack(anchor="w", padx=60)

        # Scrollable drive list
        self.drives_frame = ctk.CTkScrollableFrame(self, height=160, width=780)
        self.drives_frame.pack(padx=60, pady=(4, 16), fill="x")

        # Custom folder row
        custom_frame = ctk.CTkFrame(self, fg_color="transparent")
        custom_frame.pack(padx=60, fill="x")
        ctk.CTkLabel(
            custom_frame, text="Or choose a custom folder:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left")
        ctk.CTkButton(
            custom_frame, text="Browse…", width=100,
            command=self._browse
        ).pack(side="left", padx=8)

        # Selected path display
        self.path_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.path_label.pack(pady=4)

        # Optional new subfolder name
        self.new_folder_entry = ctk.CTkEntry(
            self, width=400,
            placeholder_text="Optional: type a new subfolder name to create"
        )
        self.new_folder_entry.pack(pady=8)

        # Continue button
        self.next_btn = ctk.CTkButton(
            self, text="Continue →", width=200, command=self._on_next,
            state="disabled", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.next_btn.pack(pady=24)

    def _load_drives(self):
        for widget in self.drives_frame.winfo_children():
            widget.destroy()
        drives = list_drives()
        if not drives:
            ctk.CTkLabel(
                self.drives_frame,
                text="No drives found. Use Browse to pick a folder."
            ).pack()
            return
        for drive in drives:
            row = ctk.CTkFrame(self.drives_frame, fg_color="gray20", corner_radius=8)
            row.pack(fill="x", pady=3, padx=4)
            tag = "External" if drive.is_external else "Internal"
            ctk.CTkLabel(
                row, text=f"{drive.name}  [{tag}]",
                font=ctk.CTkFont(size=13, weight="bold")
            ).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(
                row,
                text=f"{human_size(drive.free_bytes)} free of {human_size(drive.total_bytes)}",
                font=ctk.CTkFont(size=11), text_color="gray60"
            ).pack(side="left")
            ctk.CTkButton(
                row, text="Select", width=80,
                command=lambda p=drive.path: self._select(p)
            ).pack(side="right", padx=8)

    def _browse(self):
        path = filedialog.askdirectory(title="Choose destination folder")
        if path:
            self._select(Path(path))

    def _select(self, path: Path):
        self._selected_path = path
        self.path_label.configure(text=str(path))
        self.next_btn.configure(state="normal")

    def _restore_last(self):
        last = config.get_last_destination()
        if last and Path(last).exists():
            self._select(Path(last))

    def _on_next(self):
        if not self._selected_path:
            return
        subfolder = self.new_folder_entry.get().strip()
        dest = self._selected_path / subfolder if subfolder else self._selected_path
        dest.mkdir(parents=True, exist_ok=True)
        config.set_last_destination(str(dest))
        self.app.destination = dest
        self.app.show_screen("dates")
