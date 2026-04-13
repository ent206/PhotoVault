# src/gui/screen1_connect.py
import subprocess
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from src.models import TransferSession


class Screen1Connect(ctk.CTkFrame):
    def __init__(self, master, resume_session: Optional[TransferSession] = None):
        super().__init__(master, fg_color="transparent")
        self.app = master
        self.resume_session = resume_session
        self._polling = False
        self._poll_thread = None
        self._monitoring = False

        self.app.device = None  # Always re-verify — never trust stale state
        self._build_ui()
        self._start_polling()

    def _build_ui(self):
        # Title
        ctk.CTkLabel(
            self, text="PhotoVault",
            font=ctk.CTkFont(size=32, weight="bold")
        ).pack(pady=(60, 4))
        ctk.CTkLabel(
            self, text="iPhone Photo Transfer",
            font=ctk.CTkFont(size=14), text_color="gray60"
        ).pack(pady=(0, 40))

        # Phone icon
        self.icon_label = ctk.CTkLabel(self, text="📱", font=ctk.CTkFont(size=64))
        self.icon_label.pack(pady=8)

        # Status
        self.status_label = ctk.CTkLabel(
            self, text="Plug in your iPhone via USB",
            font=ctk.CTkFont(size=16)
        )
        self.status_label.pack(pady=12)

        self.detail_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self.detail_label.pack(pady=4)

        # Progress spinner — hidden during polling, shown once device connects
        self.spinner = ctk.CTkProgressBar(self, mode="indeterminate", width=300)

        # Retry button (hidden until error)
        self.retry_btn = ctk.CTkButton(
            self, text="Retry", command=self._retry,
            width=140, state="disabled"
        )
        self.retry_btn.pack(pady=8)

        # Action buttons shown after connection (hidden until then)
        self._action_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkButton(
            self._action_frame, text="Transfer Files →", width=200,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_screen("destination")
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            self._action_frame, text="Manage Storage", width=180,
            fg_color="gray30", hover_color="gray40",
            command=self._go_manage_storage
        ).pack(side="left", padx=8)

        # iOS 17+ sudo tunnel prompt (hidden initially)
        self.sudo_frame = ctk.CTkFrame(self, fg_color="gray20", corner_radius=10)
        ctk.CTkLabel(
            self.sudo_frame,
            text="iOS 17+ requires a background tunnel service.\n"
                 "Enter your Mac password to start it (one-time per session):",
            font=ctk.CTkFont(size=12), wraplength=380
        ).pack(pady=(16, 8), padx=20)
        self.sudo_entry = ctk.CTkEntry(
            self.sudo_frame, show="•", width=280,
            placeholder_text="Mac password"
        )
        self.sudo_entry.pack(pady=4)
        ctk.CTkButton(
            self.sudo_frame, text="Start Tunnel",
            command=self._start_tunnel, width=160
        ).pack(pady=(8, 16))

    def _show_waiting(self):
        if not self.winfo_exists():
            return
        self.status_label.configure(
            text="No iPhone detected — plug in via USB", text_color="white"
        )
        self.detail_label.configure(
            text="Waiting for device…", text_color="gray60"
        )

    def _start_polling(self):
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        import time
        self.after(0, self._show_waiting)
        error_count = 0
        last_error = None
        while self._polling:
            try:
                device = self._try_connect()
                if device:
                    self.after(0, self._on_connected, device)
                    return
            except NeedsTunnelError:
                self.after(0, self._show_tunnel_prompt)
                return
            except Exception as e:
                # Track consecutive errors
                error_count += 1
                last_error = str(e)
                # Show error after 3 consecutive failures (6 seconds)
                if error_count >= 3 and last_error:
                    self.after(0, self._on_error, last_error)
                    return
                time.sleep(2)
                continue
            time.sleep(2)

    def _try_connect(self):
        if self.app.mock_path:
            from src.device.mock_device import MockDevice
            device = MockDevice(self.app.mock_path)
            device.connect()
            return device
        # Real iPhone — just connect (fast), scan happens later on Screen 3
        from src.device.iphone_device import iPhoneDevice
        device = iPhoneDevice()
        device.connect()
        return device

    def _on_connected(self, device):
        self._polling = False
        self._navigated = False
        self.app.device = device
        info = device.device_info()
        self.retry_btn.configure(state="disabled")
        self.status_label.configure(
            text=f"Connected: {info['model']}",
            text_color="#4CAF50"
        )
        self.detail_label.configure(
            text=f"iOS {info['ios_version']}"
        )
        if self.resume_session and self.app.resume_session:
            self.after(1200, lambda: self.app.show_screen("progress"))
        else:
            self._action_frame.pack(pady=16)
            self._start_disconnect_monitor()

    def _start_disconnect_monitor(self):
        self._monitoring = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        import time
        while self._monitoring:
            time.sleep(3)
            if not self._monitoring:
                return
            try:
                alive = self.app.device and self.app.device.ping()
            except Exception:
                alive = False
            if not alive:
                self.after(0, self._on_disconnected)
                return

    def _on_disconnected(self):
        if not self.winfo_exists():
            return
        self._monitoring = False
        self._action_frame.pack_forget()
        self.spinner.pack_forget()
        self.status_label.configure(text="iPhone disconnected", text_color="#F44336")
        self.detail_label.configure(text="Plug it back in to continue.", text_color="gray60")
        self._start_polling()

    def _countdown_step(self, step: int, total_steps: int):
        if not self.winfo_exists():
            return
        pct = step / total_steps
        self.spinner.set(pct)
        if step < total_steps:
            self.after(100, self._countdown_step, step + 1, total_steps)
        else:
            self.spinner.pack_forget()
            self._action_frame.pack(pady=16)

    def _go_manage_storage(self):
        self.app.show_screen("manage_storage")

    def _on_error(self, msg: str):
        self._polling = False
        self.spinner.stop()
        self.spinner.pack_forget()
        self.status_label.configure(text="Connection Failed", text_color="#F44336")

        # Show actionable guidance based on error type
        if "StalePairing" in msg:
            detail = ("Your iPhone needs to be reconnected to establish trust.\n\n"
                     "1. Unplug your iPhone from the USB cable\n"
                     "2. Wait 2 seconds\n"
                     "3. Plug it back in\n"
                     "4. When 'Trust This Computer?' appears on your iPhone, tap 'Trust'\n"
                     "5. Click the Retry button below")
        elif "SessionConflict" in msg:
            detail = ("Finder or another app is using the iPhone connection.\n\n"
                     "Quick fix: Unplug and replug your iPhone, then click Retry.")
        elif "NoPairingRecord" in msg:
            detail = ("This iPhone hasn't been paired with this Mac.\n\n"
                     "Unplug and replug your iPhone, then tap 'Trust This Computer' on your iPhone.")
        else:
            detail = f"{msg}\n\nMake sure iPhone is unlocked, trusted, and the cable is secure."

        self.detail_label.configure(text=detail, text_color="gray70")
        self.retry_btn.configure(state="normal")

    def _retry(self):
        self.sudo_frame.pack_forget()
        self.spinner.pack_forget()
        self.retry_btn.configure(state="disabled")
        self._start_polling()

    def _show_tunnel_prompt(self):
        self.spinner.stop()
        self.spinner.pack_forget()
        self.status_label.configure(text="iOS 17+ Tunnel Required", text_color="#FF9800")
        self.sudo_frame.pack(pady=16, padx=40, fill="x")

    def _start_tunnel(self):
        password = self.sudo_entry.get()
        if not password:
            return
        try:
            proc = subprocess.Popen(
                ["sudo", "-S", "python3", "-m", "pymobiledevice3", "remote", "start-quic-tunnel"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            proc.stdin.write((password + "\n").encode())
            proc.stdin.flush()
            self.sudo_frame.pack_forget()
            self.status_label.configure(text="Tunnel started, connecting…", text_color="white")
            self.spinner.pack(pady=16)
            self.spinner.start()
            self._start_polling()
        except Exception as e:
            self.status_label.configure(
                text=f"Failed to start tunnel: {e}",
                text_color="#F44336"
            )

    def destroy(self):
        self._polling = False
        self._monitoring = False
        super().destroy()


class NeedsTunnelError(Exception):
    """Raised when iOS 17+ requires the QUIC tunnel before connection."""
    pass
