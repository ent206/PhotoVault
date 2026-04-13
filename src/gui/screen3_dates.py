import threading
from datetime import date, datetime, timedelta
from typing import Optional

import customtkinter as ctk

from src import config
from src.utils.disk_utils import check_space, human_size

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _days_in_month(month_idx: int, year: int) -> int:
    """Return number of days in a month (1-based month index)."""
    import calendar
    return calendar.monthrange(year, month_idx)[1]


class DatePicker(ctk.CTkFrame):
    """Month / Day / Year dropdown trio."""

    def __init__(self, master, initial: date, on_change, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_change = on_change

        years = [str(y) for y in range(2000, date.today().year + 1)][::-1]
        days = [str(d) for d in range(1, 32)]

        self._month_var = ctk.StringVar(value=MONTHS[initial.month - 1])
        self._day_var = ctk.StringVar(value=str(initial.day))
        self._year_var = ctk.StringVar(value=str(initial.year))

        self._month_menu = ctk.CTkOptionMenu(
            self, values=MONTHS, variable=self._month_var,
            width=130, command=self._on_month_change
        )
        self._month_menu.pack(side="left", padx=2)

        self._day_menu = ctk.CTkOptionMenu(
            self, values=days, variable=self._day_var,
            width=70, command=lambda _: self._on_change()
        )
        self._day_menu.pack(side="left", padx=2)

        self._year_menu = ctk.CTkOptionMenu(
            self, values=years, variable=self._year_var,
            width=90, command=lambda _: self._on_change()
        )
        self._year_menu.pack(side="left", padx=2)

    def _on_month_change(self, _=None):
        # Clamp day if needed
        month_idx = MONTHS.index(self._month_var.get()) + 1
        try:
            year = int(self._year_var.get())
        except ValueError:
            year = date.today().year
        max_day = _days_in_month(month_idx, year)
        days = [str(d) for d in range(1, max_day + 1)]
        self._day_menu.configure(values=days)
        if int(self._day_var.get()) > max_day:
            self._day_var.set(str(max_day))
        self._on_change()

    def get_date(self) -> date:
        month_idx = MONTHS.index(self._month_var.get()) + 1
        day = int(self._day_var.get())
        year = int(self._year_var.get())
        max_day = _days_in_month(month_idx, year)
        day = min(day, max_day)
        return date(year, month_idx, day)

    def set_date(self, d: date):
        self._month_var.set(MONTHS[d.month - 1])
        self._day_var.set(str(d.day))
        self._year_var.set(str(d.year))
        max_day = _days_in_month(d.month, d.year)
        self._day_menu.configure(values=[str(i) for i in range(1, max_day + 1)])


class Screen3Dates(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._update_thread: Optional[threading.Thread] = None
        self._pending_refresh = False
        self._scan_start_time: float = 0.0
        self._scanning = False
        self._build_ui()
        if self._is_already_scanned():
            # Mock device or previously scanned — show live preview immediately
            self._apply_preset(None)
        # else: real iPhone not yet scanned — date pickers have defaults, nothing pre-selected,
        # Continue stays disabled until user picks a preset or clicks "Use this date range"

    def _is_already_scanned(self) -> bool:
        """True for mock devices and for iPhoneDevice after scan() has been called."""
        return not (hasattr(self.app.device, 'is_scanned') and not self.app.device.is_scanned())

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
        self._preset_buttons = {}
        for label, years in [
            ("Last 1 Year", 1), ("Last 2 Years", 2),
            ("Last 3 Years", 3), ("All Media", None)
        ]:
            btn = ctk.CTkButton(
                presets_frame, text=label, width=130,
                command=lambda y=years: self._apply_preset(y),
                fg_color="gray30", hover_color="gray40"
            )
            btn.pack(side="left", padx=4)
            self._preset_buttons[years] = btn

        # Date pickers
        picker_frame = ctk.CTkFrame(self, fg_color="transparent")
        picker_frame.pack(pady=16)

        ctk.CTkLabel(
            picker_frame, text="Start:", font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(0, 6))
        last_range = config.get_last_date_range()
        if last_range:
            try:
                default_start = date.fromisoformat(last_range[0])
                default_end = date.fromisoformat(last_range[1])
            except Exception:
                default_start = date.today() - timedelta(days=365)
                default_end = date.today()
        else:
            default_start = date.today() - timedelta(days=365)
            default_end = date.today()

        self.start_picker = DatePicker(
            picker_frame,
            initial=default_start,
            on_change=lambda: None,  # Confirmed via button, not auto-refresh
        )
        self.start_picker.pack(side="left", padx=4)

        ctk.CTkLabel(
            picker_frame, text="End:", font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(16, 6))
        self.end_picker = DatePicker(
            picker_frame,
            initial=default_end,
            on_change=lambda: None,
        )
        self.end_picker.pack(side="left", padx=4)

        # "Use this date range" confirmation button
        self.select_range_btn = ctk.CTkButton(
            self, text="Use this date range",
            command=self._on_select_range,
            fg_color="gray30", hover_color="gray40", width=200
        )
        self.select_range_btn.pack(pady=(0, 8))

        # Scan progress bar (shown only during device scan, hidden otherwise)
        self.spinner = ctk.CTkProgressBar(self, width=500, mode="determinate")

        # Live preview label
        self.preview_label = ctk.CTkLabel(
            self, text="Select a preset or enter a date range above",
            font=ctk.CTkFont(size=15), text_color="gray60"
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

        # Navigation buttons
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(pady=20)
        self.back_btn = ctk.CTkButton(
            nav_frame, text="← Back", width=140, command=self._on_back,
            fg_color="gray30", hover_color="gray40"
        )
        self.back_btn.pack(side="left", padx=8)
        self.next_btn = ctk.CTkButton(
            nav_frame, text="Continue →", width=200, command=self._on_next,
            state="disabled", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.next_btn.pack(side="left", padx=8)

    def _apply_preset_dates_only(self, years: Optional[int]):
        """Set preset date range without triggering a preview refresh (pre-scan)."""
        for y, btn in self._preset_buttons.items():
            btn.configure(fg_color="#1f538d" if y == years else "gray30")
        end = date.today()
        start = date(2000, 1, 1) if years is None else end - timedelta(days=365 * years)
        self.start_picker.set_date(start)
        self.end_picker.set_date(end)

    def _apply_preset(self, years: Optional[int]):
        for y, btn in self._preset_buttons.items():
            btn.configure(fg_color="#1f538d" if y == years else "gray30")
        # Reset "Use this date range" button to default (preset takes over)
        self.select_range_btn.configure(fg_color="gray30", text="Use this date range")
        end = date.today()
        start = date(2000, 1, 1) if years is None else end - timedelta(days=365 * years)
        self.start_picker.set_date(start)
        self.end_picker.set_date(end)
        if self._is_already_scanned():
            self._refresh_preview()
        else:
            label = "All Media" if years is None else f"Last {years} Year{'s' if years > 1 else ''}"
            self.preview_label.configure(
                text=f"{label} selected — click Continue to scan"
            )
            self.next_btn.configure(state="normal")

    def _refresh_preview(self):
        if not self._is_already_scanned():
            return
        self._pending_refresh = True
        if self._update_thread and self._update_thread.is_alive():
            return
        self._start_refresh_thread()

    def _start_refresh_thread(self):
        self._pending_refresh = False
        self.preview_label.configure(text="Calculating…")
        # Read dates on the main thread — tkinter StringVars are not thread-safe
        start = datetime.combine(self.start_picker.get_date(), datetime.min.time())
        end = datetime.combine(self.end_picker.get_date(), datetime.max.time())
        self._update_thread = threading.Thread(
            target=self._compute_preview, args=(start, end), daemon=True
        )
        self._update_thread.start()

    def _compute_preview(self, start: datetime, end: datetime):
        try:
            assets = self.app.device.list_assets(start, end)
            photos = sum(1 for a in assets if a.media_type in ("photo", "live_photo_image"))
            videos = sum(1 for a in assets if a.media_type in ("video", "live_photo_video"))
            total_bytes = sum(a.file_size for a in assets)
            stubs = [a for a in assets if a.is_icloud_stub]
            space = check_space(self.app.destination, total_bytes)
            self.after(0, self._update_ui, assets, photos, videos, total_bytes, stubs, space)
        except Exception as e:
            self.after(0, lambda: self.preview_label.configure(
                text=f"Error calculating preview: {e}"
            ))
        finally:
            if self._pending_refresh:
                self.after(0, self._start_refresh_thread)

    def _update_ui(self, assets, photos, videos, total_bytes, stubs, space):
        if not self.winfo_exists():
            return
        self.app.selected_assets = assets

        if not assets:
            self.preview_label.configure(
                text="No media found in this date range — try adjusting the dates"
            )
            self.next_btn.configure(state="disabled")
            self.stub_warning.configure(text="")
            self.space_warning.configure(text="")
            return

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
            if space["free"] == 0:
                msg = "✗ Destination drive is not accessible. Go back and reselect it."
            else:
                msg = (f"✗ Not enough space. Need {human_size(total_bytes)}, "
                       f"only {human_size(space['free'])} available on destination.")
            self.space_warning.configure(text=msg)
            self.next_btn.configure(state="disabled")
        elif space["headroom_pct"] < 10:
            self.space_warning.configure(
                text=f"⚠ Low disk space: only {space['headroom_pct']:.0f}% headroom after transfer."
            )
            self.next_btn.configure(state="normal" if assets else "disabled")
        else:
            self.space_warning.configure(text="")
            self.next_btn.configure(state="normal" if assets else "disabled")

    def _on_select_range(self):
        """User confirmed a custom date range via the button."""
        # Deselect all preset buttons
        for btn in self._preset_buttons.values():
            btn.configure(fg_color="gray30")
        # Show the button as confirmed
        start = self.start_picker.get_date()
        end = self.end_picker.get_date()
        self.select_range_btn.configure(
            fg_color="#1f538d",
            text=f"✓ {start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"
        )
        if self._is_already_scanned():
            self._refresh_preview()
        else:
            self.preview_label.configure(
                text=f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')} selected — click Continue to scan"
            )
            self.next_btn.configure(state="normal")

    def _on_back(self):
        if self._scanning:
            return
        self.app.show_screen("destination")

    def _on_next(self):
        if self._scanning:
            return
        if not self._is_already_scanned():
            self._start_scan_then_proceed()
        else:
            self.app.show_screen("summary")

    def _start_scan_then_proceed(self):
        import time
        self._scanning = True
        self._scan_start_time = time.time()
        # Read dates on main thread before handing off to background thread
        self._scan_start_date = datetime.combine(self.start_picker.get_date(), datetime.min.time())
        self._scan_end_date = datetime.combine(self.end_picker.get_date(), datetime.max.time())
        config.set_last_date_range(
            self.start_picker.get_date().isoformat(),
            self.end_picker.get_date().isoformat(),
        )
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        self.preview_label.configure(text="Connecting to iPhone…")
        self.spinner.configure(mode="indeterminate")
        self.spinner.pack(pady=8)
        self.spinner.start()
        threading.Thread(target=self._run_scan_then_proceed, daemon=True).start()

    def _run_scan_then_proceed(self):
        try:
            self.app.device.scan(
                on_progress=lambda cur, tot: self.after(0, self._on_scan_progress, cur, tot),
                on_db_progress=lambda rd, tot, el: self.after(0, self._on_db_progress, rd, tot, el),
                start_date=self._scan_start_date,
                end_date=self._scan_end_date,
            )
        except Exception as e:
            self.after(0, self._on_scan_error, str(e))
            return
        self.after(0, self._on_scan_done_proceed)

    def _on_db_progress(self, read: int, total: int, elapsed: float):
        if not self.winfo_exists():
            return
        self.spinner.stop()
        self.spinner.configure(mode="determinate")
        pct = read / total if total > 0 else 0
        self.spinner.set(pct)
        read_mb = read / 1_048_576
        total_mb = total / 1_048_576
        if read >= total:
            self.preview_label.configure(text="Analyzing database…")
        elif elapsed > 0.5 and read > 0:
            speed = read / elapsed
            eta = int((total - read) / speed)
            eta_str = f"{eta}s" if eta < 60 else f"{eta // 60}m {eta % 60}s"
            self.preview_label.configure(
                text=f"Downloading database… {read_mb:.0f} of {total_mb:.0f} MB  ·  {eta_str} remaining"
            )
        else:
            self.preview_label.configure(
                text=f"Downloading database… {read_mb:.0f} of {total_mb:.0f} MB"
            )

    def _on_scan_progress(self, current: int, total: int):
        import time
        if not self.winfo_exists():
            return
        if total == 1 and current == 1:
            self.spinner.stop()
            self.spinner.configure(mode="determinate")
            self.preview_label.configure(text="Processing results…")
            self.spinner.set(1.0)
            return
        if total > 1:
            # EXIF fallback path — determinate per-file progress
            self.spinner.stop()
            self.spinner.configure(mode="determinate")
            self.spinner.set(current / total)
            elapsed = time.time() - self._scan_start_time
            if current > 5 and elapsed > 0:
                rate = current / elapsed
                remaining = (total - current) / rate
                eta = f"~{int(remaining)}s" if remaining < 60 else f"~{int(remaining/60)}m"
                self.preview_label.configure(
                    text=f"Scanning {current:,} of {total:,} files  •  {eta} remaining"
                )

    def _on_scan_error(self, error: str):
        if not self.winfo_exists():
            return
        self._scanning = False
        self.spinner.pack_forget()
        self.preview_label.configure(
            text=f"Scan failed: {error}",
            text_color="#F44336"
        )
        self.back_btn.configure(state="normal")
        self.next_btn.configure(state="disabled")

    def _on_scan_done_proceed(self):
        if not self.winfo_exists():
            return
        self._scanning = False
        self.spinner.pack_forget()
        assets = self.app.device.list_assets(self._scan_start_date, self._scan_end_date)
        if not assets:
            self.preview_label.configure(
                text="No photos or videos found in that date range — try adjusting the dates",
                text_color="#FF9800"
            )
            self.back_btn.configure(state="normal")
            self.next_btn.configure(state="disabled")
            return
        self.app.selected_assets = assets
        self.app.show_screen("summary")
