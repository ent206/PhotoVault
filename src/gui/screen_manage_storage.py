# src/gui/screen_manage_storage.py
import threading
from datetime import date, datetime, timedelta
from typing import List, Optional

import customtkinter as ctk

from src import config
from src.gui.screen3_dates import DatePicker
from src.models import PhotoAsset
from src.utils.disk_utils import human_size

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

_FILTER_ALL         = "all"
_FILTER_PHOTOS      = "photos"
_FILTER_VIDEOS      = "videos"
_FILTER_SCREENSHOTS = "screenshots"


def _apply_filter(assets: List[PhotoAsset], ftype: str) -> List[PhotoAsset]:
    if ftype == _FILTER_PHOTOS:
        return [a for a in assets if a.media_type in ("photo", "live_photo_image") and not a.is_screenshot]
    if ftype == _FILTER_VIDEOS:
        return [a for a in assets if a.media_type in ("video", "live_photo_video")]
    if ftype == _FILTER_SCREENSHOTS:
        return [a for a in assets if a.is_screenshot]
    return assets  # all


class ScreenManageStorage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self._all_assets: List[PhotoAsset] = []
        self._filtered_assets: List[PhotoAsset] = []
        self._active_filter = _FILTER_ALL
        self._scanning = False
        self._deleting = False
        self._scan_start: Optional[datetime] = None
        self._scan_end: Optional[datetime] = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="Free Up iPhone Storage",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(28, 4))
        ctk.CTkLabel(
            self, text="Select a date range, preview what will be deleted, then confirm.",
            font=ctk.CTkFont(size=13), text_color="gray60"
        ).pack(pady=(0, 16))

        # ── Presets ──
        presets_frame = ctk.CTkFrame(self, fg_color="transparent")
        presets_frame.pack(pady=(0, 4))
        self._preset_btns = {}
        for label, years in [("Last 1 Year", 1), ("Last 2 Years", 2),
                              ("Last 3 Years", 3), ("All Media", None)]:
            btn = ctk.CTkButton(
                presets_frame, text=label, width=130,
                command=lambda y=years: self._apply_preset(y),
                fg_color="gray30", hover_color="gray40"
            )
            btn.pack(side="left", padx=4)
            self._preset_btns[years] = btn

        # ── Date pickers ──
        picker_frame = ctk.CTkFrame(self, fg_color="transparent")
        picker_frame.pack(pady=8)

        last_range = config.get_last_date_range()
        if last_range:
            try:
                default_start = date.fromisoformat(last_range[0])
                default_end   = date.fromisoformat(last_range[1])
            except Exception:
                default_start = date.today() - timedelta(days=365)
                default_end   = date.today()
        else:
            default_start = date.today() - timedelta(days=365)
            default_end   = date.today()

        ctk.CTkLabel(picker_frame, text="Start:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 6))
        self.start_picker = DatePicker(picker_frame, initial=default_start, on_change=lambda: None)
        self.start_picker.pack(side="left", padx=4)
        ctk.CTkLabel(picker_frame, text="End:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(16, 6))
        self.end_picker = DatePicker(picker_frame, initial=default_end, on_change=lambda: None)
        self.end_picker.pack(side="left", padx=4)

        # ── Preview button + progress bar ──
        self.preview_btn = ctk.CTkButton(
            self, text="Preview Files", width=180,
            command=self._start_scan
        )
        self.preview_btn.pack(pady=10)

        self.progress_bar = ctk.CTkProgressBar(self, width=500, mode="indeterminate")
        self.progress_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color="gray60")

        # ── Results area (hidden until scan completes) ──
        self.results_frame = ctk.CTkFrame(self, fg_color="transparent")

        # Filter toggles
        filter_row = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        filter_row.pack(pady=(8, 4))
        self._filter_btns = {}
        for label, ftype in [("Everything", _FILTER_ALL), ("Photos", _FILTER_PHOTOS),
                              ("Videos", _FILTER_VIDEOS), ("Screenshots", _FILTER_SCREENSHOTS)]:
            btn = ctk.CTkButton(
                filter_row, text=label, width=130,
                command=lambda f=ftype: self._set_filter(f),
                fg_color="#1f538d" if ftype == _FILTER_ALL else "gray30",
                hover_color="gray40"
            )
            btn.pack(side="left", padx=4)
            self._filter_btns[ftype] = btn

        # ⓘ info button — appears right of Screenshots, shows tooltip bubble
        self._info_btn = ctk.CTkButton(
            filter_row, text="ⓘ", width=28, height=28,
            fg_color="transparent", hover_color="gray30",
            font=ctk.CTkFont(size=15),
            command=self._toggle_screenshot_tip
        )
        self._tip_window = None

        # Count + size
        self.count_label = ctk.CTkLabel(
            self.results_frame, text="",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.count_label.pack(pady=(8, 2))

        self.breakdown_label = ctk.CTkLabel(
            self.results_frame, text="",
            font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.breakdown_label.pack(pady=(0, 8))

        # Delete button
        self.delete_btn = ctk.CTkButton(
            self.results_frame,
            text="Delete Files",
            width=220, height=44,
            fg_color="#c62828", hover_color="#8b0000",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
            command=self._confirm_deletion
        )
        self.delete_btn.pack(pady=(4, 12))

        # ── Deletion progress (hidden until deletion starts) ──
        self.deletion_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.deletion_progress = ctk.CTkProgressBar(self.deletion_frame, width=500, mode="determinate")
        self.deletion_progress.pack(pady=8)
        self.deletion_progress.set(0)
        self.deletion_label = ctk.CTkLabel(
            self.deletion_frame, text="",
            font=ctk.CTkFont(size=13)
        )
        self.deletion_label.pack(pady=4)
        self.freed_label = ctk.CTkLabel(
            self.deletion_frame, text="",
            font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.freed_label.pack(pady=2)

        # ── Back button (always visible) ──
        self.back_btn = ctk.CTkButton(
            self, text="← Back", width=120,
            fg_color="gray30", hover_color="gray40",
            command=self._go_back
        )
        self.back_btn.pack(pady=(8, 16))

    # ------------------------------------------------------------------ #
    # Preset handling                                                      #
    # ------------------------------------------------------------------ #

    def _apply_preset(self, years: Optional[int]):
        for y, btn in self._preset_btns.items():
            btn.configure(fg_color="#1f538d" if y == years else "gray30")
        end = date.today()
        start = date(2000, 1, 1) if years is None else end - timedelta(days=365 * years)
        self.start_picker.set_date(start)
        self.end_picker.set_date(end)

    # ------------------------------------------------------------------ #
    # Scan                                                                 #
    # ------------------------------------------------------------------ #

    def _start_scan(self):
        if self._scanning or self._deleting:
            return
        self._scanning = True
        self._all_assets = []
        self._filtered_assets = []
        self.results_frame.pack_forget()
        self.deletion_frame.pack_forget()

        self._scan_start = datetime.combine(self.start_picker.get_date(), datetime.min.time())
        self._scan_end   = datetime.combine(self.end_picker.get_date(),   datetime.max.time())

        self.preview_btn.configure(state="disabled")
        self.progress_label.configure(text="Connecting to iPhone…")
        self.progress_label.pack(pady=(4, 0))
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.pack(pady=4)
        self.progress_bar.start()

        self.app.device.reset_scan()
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        try:
            self.app.device.scan(
                on_progress=lambda cur, tot: self.after(0, self._on_scan_progress, cur, tot),
                on_db_progress=lambda rd, tot, el: self.after(0, self._on_db_progress, rd, tot, el),
                start_date=self._scan_start,
                end_date=self._scan_end,
            )
        except Exception as e:
            self.after(0, self._on_scan_error, str(e))
            return
        assets = self.app.device.list_assets(self._scan_start, self._scan_end)
        self.after(0, self._on_scan_done, assets)

    def _on_db_progress(self, read: int, total: int, elapsed: float):
        if not self.winfo_exists():
            return
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        pct = read / total if total > 0 else 0
        self.progress_bar.set(pct)
        read_mb = read / 1_048_576
        total_mb = total / 1_048_576
        if read >= total:
            self.progress_label.configure(text="Analyzing database…")
        elif elapsed > 0.5 and read > 0:
            speed = read / elapsed
            eta = int((total - read) / speed)
            eta_str = f"{eta}s" if eta < 60 else f"{eta // 60}m {eta % 60}s"
            self.progress_label.configure(
                text=f"Downloading database… {read_mb:.0f} of {total_mb:.0f} MB  ·  {eta_str} remaining"
            )
        else:
            self.progress_label.configure(
                text=f"Downloading database… {read_mb:.0f} of {total_mb:.0f} MB"
            )

    def _on_scan_progress(self, current: int, total: int):
        if not self.winfo_exists():
            return
        if total == 1 and current == 1:
            self.progress_label.configure(text="Processing results…")
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1.0)
        elif total > 1:
            # EXIF fallback path
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(current / total)
            self.progress_label.configure(text=f"Scanning {current:,} of {total:,} files…")

    def _on_scan_error(self, msg: str):
        if not self.winfo_exists():
            return
        self._scanning = False
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        disconnected = any(k in msg.lower() for k in ("pipe", "connect", "socket", "timeout", "eof"))
        if disconnected:
            self.progress_label.configure(
                text="iPhone disconnected — plug it back in and try again.", text_color="#F44336"
            )
        else:
            self.progress_label.configure(text=f"Scan failed: {msg}", text_color="#F44336")
        self.preview_btn.configure(state="normal")

    def _on_scan_done(self, assets: List[PhotoAsset]):
        if not self.winfo_exists():
            return
        self._scanning = False
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()
        self.preview_btn.configure(state="normal")

        self._all_assets = assets
        self._set_filter(self._active_filter)
        self.results_frame.pack(fill="x", padx=20)

    # ------------------------------------------------------------------ #
    # Filter                                                               #
    # ------------------------------------------------------------------ #

    def _set_filter(self, ftype: str):
        self._active_filter = ftype
        for f, btn in self._filter_btns.items():
            btn.configure(fg_color="#1f538d" if f == ftype else "gray30")

        # Show ⓘ button only when Screenshots filter is active
        if ftype == _FILTER_SCREENSHOTS:
            self._info_btn.pack(side="left", padx=(2, 0))
            self.after(50, self._toggle_screenshot_tip)  # slight delay so button is laid out first
        else:
            self._info_btn.pack_forget()
            self._close_screenshot_tip()

        self._filtered_assets = _apply_filter(self._all_assets, ftype)
        total = len(self._filtered_assets)
        size  = sum(a.file_size for a in self._filtered_assets)

        if total == 0:
            self.count_label.configure(text="No files in this range")
            self.breakdown_label.configure(text="")
            self.delete_btn.configure(state="disabled", text="Delete Files")
        else:
            size_str = human_size(size) if size > 0 else "size unavailable"
            self.count_label.configure(text=f"{total:,} files  ·  {size_str}")
            photos      = sum(1 for a in self._all_assets if a.media_type in ("photo", "live_photo_image") and not a.is_screenshot)
            videos      = sum(1 for a in self._all_assets if a.media_type in ("video", "live_photo_video"))
            screenshots = sum(1 for a in self._all_assets if a.is_screenshot)
            self.breakdown_label.configure(
                text=f"{photos:,} photos  ·  {videos:,} videos  ·  {screenshots:,} screenshots"
            )
            self._refresh_delete_btn()

    def _refresh_delete_btn(self):
        n = len(self._filtered_assets)
        if n == 0:
            self.delete_btn.configure(state="disabled", text="Delete Files")
        else:
            self.delete_btn.configure(state="normal", text=f"Delete {n:,} Files")

    # ------------------------------------------------------------------ #
    # Deletion                                                             #
    # ------------------------------------------------------------------ #

    def _confirm_deletion(self):
        if self._deleting or not self._filtered_assets:
            return
        n = len(self._filtered_assets)

        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Deletion")
        dialog.resizable(False, False)
        dialog.grab_set()

        # Center over the app window
        self.update_idletasks()
        aw = self.winfo_toplevel()
        ax, ay = aw.winfo_x(), aw.winfo_y()
        aw_w, aw_h = aw.winfo_width(), aw.winfo_height()
        dw, dh = 460, 280
        x = ax + (aw_w - dw) // 2
        y = ay + (aw_h - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="Permanently Delete Files?",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(28, 8))

        ctk.CTkLabel(
            dialog,
            text=f"{n:,} files will be permanently deleted from your iPhone\n"
                 "and cannot be recovered. Make sure you have a backup.",
            font=ctk.CTkFont(size=13), text_color="gray70",
            wraplength=380, justify="center"
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack()

        def on_confirm():
            dialog.destroy()
            self._start_deletion()

        ctk.CTkButton(
            btn_frame, text=f"Delete {n:,} Files",
            width=180, height=40,
            fg_color="#c62828", hover_color="#8b0000",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=on_confirm
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame, text="Cancel", width=120, height=40,
            fg_color="gray30", hover_color="gray40",
            command=dialog.destroy
        ).pack(side="left", padx=8)

    def _start_deletion(self):
        if self._deleting or not self._filtered_assets:
            return
        self._deleting = True
        self.results_frame.pack_forget()
        self.preview_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        self.deletion_progress.set(0)
        self.deletion_label.configure(text="Starting…", text_color="white")
        self.freed_label.configure(text="")
        self.deletion_frame.pack(pady=8)
        threading.Thread(target=self._run_deletion, daemon=True).start()

    def _run_deletion(self):
        assets = list(self._filtered_assets)
        total  = len(assets)
        deleted = 0
        failed  = 0
        freed   = 0

        for i, asset in enumerate(assets):
            self.after(0, self._update_deletion_progress, i, total, freed)
            try:
                self.app.device.delete_file(asset)
                deleted += 1
                freed   += asset.file_size
            except Exception:
                failed += 1

        self.after(0, self._on_deletion_done, deleted, failed, freed)

    def _update_deletion_progress(self, done: int, total: int, freed: int):
        if not self.winfo_exists():
            return
        pct = done / total if total else 0
        self.deletion_progress.set(pct)
        self.deletion_label.configure(text=f"Deleting {done:,} of {total:,} files…")
        if freed > 0:
            self.freed_label.configure(text=f"Freed {human_size(freed)} so far")

    def _on_deletion_done(self, deleted: int, failed: int, freed: int):
        if not self.winfo_exists():
            return
        self._deleting = False
        self.deletion_progress.set(1.0)
        total = deleted + failed
        if failed == 0:
            self.deletion_label.configure(
                text=f"Done — deleted {deleted:,} files and freed {human_size(freed)}",
                text_color="#4CAF50"
            )
        elif deleted == 0:
            self.deletion_label.configure(
                text="No files were deleted — iPhone may have been disconnected.",
                text_color="#F44336"
            )
        else:
            self.deletion_label.configure(
                text=f"Done — deleted {deleted:,} of {total:,} files, freed {human_size(freed)}  "
                     f"({failed} failed — iPhone may have disconnected mid-way)",
                text_color="#FF9800"
            )
        self.freed_label.configure(text="")
        self.back_btn.configure(state="normal")
        self.preview_btn.configure(state="normal")

    # ------------------------------------------------------------------ #
    # Screenshot tooltip                                                   #
    # ------------------------------------------------------------------ #

    def _toggle_screenshot_tip(self):
        if self._tip_window and self._tip_window.winfo_exists():
            self._close_screenshot_tip()
            return
        tip = ctk.CTkToplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        self._tip_window = tip

        frame = ctk.CTkFrame(
            tip, fg_color="gray20", corner_radius=10,
            border_width=1, border_color="gray40"
        )
        frame.pack(fill="both", expand=True)

        close_row = ctk.CTkFrame(frame, fg_color="transparent")
        close_row.pack(fill="x", padx=6, pady=(6, 0))
        ctk.CTkButton(
            close_row, text="✕", width=22, height=22,
            fg_color="transparent", hover_color="gray35",
            font=ctk.CTkFont(size=11),
            command=self._close_screenshot_tip
        ).pack(side="right")

        ctk.CTkLabel(
            frame,
            text="Screenshots are images captured using the\n"
                 "side button + volume up — regardless of\n"
                 "what's on screen. This includes screenshotted\n"
                 "texts, maps, webpages, and more.",
            font=ctk.CTkFont(size=12), text_color="gray80",
            justify="left"
        ).pack(padx=14, pady=(2, 14))

        tip.update_idletasks()
        bx = self._info_btn.winfo_rootx()
        by = self._info_btn.winfo_rooty()
        bw = self._info_btn.winfo_width()
        tw = tip.winfo_reqwidth()
        th = tip.winfo_reqheight()
        x = bx + bw // 2 - tw // 2
        y = by - th - 6
        tip.geometry(f"+{x}+{y}")

    def _close_screenshot_tip(self):
        if self._tip_window and self._tip_window.winfo_exists():
            self._tip_window.destroy()
        self._tip_window = None

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _go_back(self):
        if self._scanning or self._deleting:
            return
        self.app.show_screen("connect")
