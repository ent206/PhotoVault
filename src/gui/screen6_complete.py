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
        all_passed = len(failed_files) == 0

        title = "Transfer Complete ✓" if all_passed else "Transfer Complete — Some Files Failed"
        title_color = "#4CAF50" if all_passed else "#FF9800"

        ctk.CTkLabel(
            self, text=title,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=title_color
        ).pack(pady=(50, 16))

        # Results table
        info_frame = ctk.CTkFrame(self, fg_color="gray15", corner_radius=12)
        info_frame.pack(padx=80, pady=8, fill="x")

        rows = [
            ("Transferred Successfully", f"{results['completed']:,} files"),
            ("Skipped (duplicates)", f"{results['skipped']:,} files"),
            ("Failed Verification", f"{results['failed']:,} files"),
        ]
        for label, value in rows:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=12),
                text_color="gray60", width=240, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=ctk.CTkFont(size=13), anchor="w"
            ).pack(side="left")

        if all_passed:
            # Green delete button — ONLY shown when 100% success
            ctk.CTkButton(
                self,
                text="🗑  Free Up Space on iPhone",
                width=280, height=44,
                fg_color="#4CAF50", hover_color="#388E3C",
                command=self._go_delete,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(pady=24)
        else:
            # Failed files list + retry — delete button is completely absent
            ctk.CTkLabel(
                self,
                text="The following files failed verification. Fix and retry before deleting from iPhone:",
                font=ctk.CTkFont(size=12), text_color="#F44336", wraplength=600
            ).pack(pady=(16, 4))

            box = ctk.CTkScrollableFrame(self, height=100, width=600, fg_color="gray20")
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
            ).pack(pady=16)

        # Done button always present
        ctk.CTkButton(
            self, text="Done", width=140, fg_color="gray40",
            command=lambda: self.app.show_screen("connect")
        ).pack(pady=8)

    def _go_delete(self):
        self.app.show_screen("delete")

    def _retry_failed(self):
        results = self.app.transfer_results
        failed_names = set(results.get("failed_files", []))
        self.app.selected_assets = [
            a for a in self.app.selected_assets if a.filename in failed_names
        ]
        self.app.show_screen("summary")
