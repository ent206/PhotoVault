import customtkinter as ctk

from src.utils.disk_utils import human_size


class Screen6Complete(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._build_ui()

    def _build_ui(self):
        results = self.app.transfer_results
        failed_files = results.get("failed_files", [])
        completed = results["completed"]
        skipped = results["skipped"]
        failed = results["failed"]
        safe = completed + skipped  # files confirmed on destination

        no_failures = failed == 0

        if no_failures:
            title = "Transfer Complete ✓"
            title_color = "#4CAF50"
        else:
            title = "Transfer Complete — 1 File Could Not Be Read" if failed == 1 \
                else f"Transfer Complete — {failed} Files Could Not Be Read"
            title_color = "#FF9800"

        ctk.CTkLabel(
            self, text=title,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=title_color
        ).pack(pady=(24, 8))

        # Results table
        info_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=12)
        info_frame.pack(padx=80, pady=4, fill="x")

        rows = [
            ("Newly transferred", f"{completed:,} files"),
            ("Already on destination", f"{skipped:,} files"),
            ("Safely backed up (total)", f"{safe:,} files"),
        ]
        if failed:
            rows.append(("Could not be read", f"{failed:,} file{'s' if failed != 1 else ''}"))

        for i, (label, value) in enumerate(rows):
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            # Separator before the total row
            if i == 2:
                ctk.CTkFrame(info_frame, fg_color="gray30", height=1).pack(fill="x", padx=20)
                row = ctk.CTkFrame(info_frame, fg_color="transparent")
                row.pack(fill="x", padx=20, pady=4)
            label_color = "#F44336" if label == "Could not be read" else "gray60"
            value_color = "#F44336" if label == "Could not be read" else "white"
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=12),
                text_color=label_color, width=240, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=ctk.CTkFont(size=13),
                text_color=value_color, anchor="w"
            ).pack(side="left")

        if safe > 0:
            # Show delete button whenever files are safely on destination
            delete_note = "" if no_failures else f"  ({failed} unreadable file{'s' if failed != 1 else ''} will not be deleted)"
            ctk.CTkButton(
                self,
                text="🗑  Free Up Space on iPhone",
                width=300, height=44,
                fg_color="#4CAF50", hover_color="#388E3C",
                command=self._go_delete,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(pady=(12, 0))
            if delete_note:
                ctk.CTkLabel(
                    self, text=delete_note,
                    font=ctk.CTkFont(size=11), text_color="gray60"
                ).pack(pady=(2, 8))

        if not no_failures:
            # Failed files list + retry — delete button is completely absent
            ctk.CTkLabel(
                self,
                text="These files could not be read from the iPhone (likely corrupted). "
                     "All other files are safely backed up.",
                font=ctk.CTkFont(size=12), text_color="gray60", wraplength=600
            ).pack(pady=(16, 4))

            box = ctk.CTkScrollableFrame(self, height=160, width=600, fg_color="gray20")
            box.pack(padx=80, pady=4)
            for fname in failed_files:
                ctk.CTkLabel(
                    box, text=fname, font=ctk.CTkFont(size=11),
                    text_color="#F44336"
                ).pack(anchor="w", padx=8, pady=2)

            ctk.CTkButton(
                self, text="Retry Failed Files", width=200,
                command=self._retry_failed,
                fg_color="#FF9800", hover_color="#E65100"
            ).pack(pady=12)

        # Navigation buttons
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(pady=(12, 8))

        ctk.CTkButton(
            nav_frame, text="Transfer More Files", width=180,
            command=self._transfer_more,
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            nav_frame, text="Manage Storage", width=160,
            command=lambda: self.app.show_screen("manage_storage"),
            fg_color="gray30", hover_color="gray40"
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            nav_frame, text="Done", width=120, fg_color="gray40",
            command=lambda: self.app.show_screen("connect")
        ).pack(side="left", padx=8)

    def _go_delete(self):
        self.app.show_screen("delete")

    def _transfer_more(self):
        """Go back to date picker with device still connected."""
        self.app.selected_assets = []
        self.app.transfer_results = {}
        if self.app.device:
            self.app.device.reset_scan()
        self.app.show_screen("dates")

    def _retry_failed(self):
        results = self.app.transfer_results
        failed_names = set(results.get("failed_files", []))
        self.app.selected_assets = [
            a for a in self.app.selected_assets if a.filename in failed_names
        ]
        self.app.show_screen("summary")
