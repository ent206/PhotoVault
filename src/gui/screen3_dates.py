import threading
from datetime import date, datetime, timedelta
from typing import Optional

import customtkinter as ctk
from tkcalendar import DateEntry

from src.utils.disk_utils import check_space, human_size


class Screen3Dates(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._update_thread: Optional[threading.Thread] = None
        self._pending_refresh = False
        self._build_ui()
        self._refresh_preview()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Select Date Range",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(40, 4))
        ctk.CTkLabel(
            self, text="Choose which photos and videos to transfer",
            font=ctk.CTkFont(size=13), text_color="gray60"
        ).pack(pady=(0, 20))

        # Quick preset buttons
        presets_frame = ctk.CTkFrame(self, fg_color="transparent")
        presets_frame.pack(pady=8)
        for label, years in [
            ("Last 1 Year", 1), ("Last 2 Years", 2),
            ("Last 3 Years", 3), ("All Photos", None)
        ]:
            ctk.CTkButton(
                presets_frame, text=label, width=130,
                command=lambda y=years: self._apply_preset(y),
                fg_color="gray30", hover_color="gray40"
            ).pack(side="left", padx=4)

        # Date pickers
        picker_frame = ctk.CTkFrame(self, fg_color="transparent")
        picker_frame.pack(pady=16)

        ctk.CTkLabel(
            picker_frame, text="Start Date:", font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(0, 8))
        self.start_entry = DateEntry(
            picker_frame, width=14, background="gray20",
            foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd"
        )
        self.start_entry.pack(side="left", padx=8)
        self.start_entry.set_date(date.today() - timedelta(days=365))
        self.start_entry.bind("<<DateEntrySelected>>", lambda _: self._refresh_preview())

        ctk.CTkLabel(
            picker_frame, text="End Date:", font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(16, 8))
        self.end_entry = DateEntry(
            picker_frame, width=14, background="gray20",
            foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd"
        )
        self.end_entry.pack(side="left", padx=8)
        self.end_entry.set_date(date.today())
        self.end_entry.bind("<<DateEntrySelected>>", lambda _: self._refresh_preview())

        # Live preview label
        self.preview_label = ctk.CTkLabel(
            self, text="Calculating…", font=ctk.CTkFont(size=15)
        )
        self.preview_label.pack(pady=16)

        # iCloud stub warning
        self.stub_warning = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color="#FF9800", wraplength=600
        )
        self.stub_warning.pack(pady=4)

        # Space warning
        self.space_warning = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color="#F44336", wraplength=600
        )
        self.space_warning.pack(pady=4)

        # Continue button
        self.next_btn = ctk.CTkButton(
            self, text="Continue →", width=200, command=self._on_next,
            state="disabled", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.next_btn.pack(pady=20)

    def _apply_preset(self, years: Optional[int]):
        end = date.today()
        start = date(2000, 1, 1) if years is None else end - timedelta(days=365 * years)
        self.start_entry.set_date(start)
        self.end_entry.set_date(end)
        self._refresh_preview()

    def _refresh_preview(self):
        self._pending_refresh = True
        if self._update_thread and self._update_thread.is_alive():
            # Thread is running; will re-trigger after it completes
            return
        self._start_refresh_thread()

    def _start_refresh_thread(self):
        self._pending_refresh = False
        self.preview_label.configure(text="Calculating…")
        self._update_thread = threading.Thread(target=self._compute_preview, daemon=True)
        self._update_thread.start()

    def _compute_preview(self):
        try:
            start = datetime.combine(self.start_entry.get_date(), datetime.min.time())
            end = datetime.combine(self.end_entry.get_date(), datetime.max.time())
            assets = self.app.device.list_assets(start, end)
            photos = sum(
                1 for a in assets if a.media_type in ("photo", "live_photo_image")
            )
            videos = sum(
                1 for a in assets if a.media_type in ("video", "live_photo_video")
            )
            total_bytes = sum(a.file_size for a in assets)
            stubs = [a for a in assets if a.is_icloud_stub]
            space = check_space(self.app.destination, total_bytes)
            self.after(0, self._update_ui, assets, photos, videos, total_bytes, stubs, space)
        except Exception as e:
            self.after(0, lambda: self.preview_label.configure(
                text=f"Error calculating preview: {e}"
            ))
        finally:
            # Re-trigger if a refresh was requested while we were computing
            if self._pending_refresh:
                self.after(0, self._start_refresh_thread)

    def _update_ui(self, assets, photos, videos, total_bytes, stubs, space):
        self.app.selected_assets = assets
        self.preview_label.configure(
            text=f"{photos:,} photos  •  {videos:,} videos  •  {human_size(total_bytes)}"
        )

        if stubs:
            self.stub_warning.configure(
                text=f"⚠ {len(stubs)} file(s) appear to be iCloud placeholders "
                     "(low-res previews, not full originals). Enable 'Download and Keep Originals' "
                     "in iPhone Settings → Photos before transferring."
            )
        else:
            self.stub_warning.configure(text="")

        if not space["ok"]:
            self.space_warning.configure(
                text=f"✗ Not enough space. Need {human_size(total_bytes)}, "
                     f"only {human_size(space['free'])} available on destination."
            )
            self.next_btn.configure(state="disabled")
        elif space["headroom_pct"] < 10:
            self.space_warning.configure(
                text=f"⚠ Low disk space: only {space['headroom_pct']:.0f}% headroom after transfer."
            )
            self.next_btn.configure(state="normal" if assets else "disabled")
        else:
            self.space_warning.configure(text="")
            self.next_btn.configure(state="normal" if assets else "disabled")

    def _on_next(self):
        self.app.show_screen("summary")
