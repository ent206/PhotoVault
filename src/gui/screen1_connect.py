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

        # Progress spinner
        self.spinner = ctk.CTkProgressBar(self, mode="indeterminate", width=300)
        self.spinner.pack(pady=16)
        self.spinner.start()

        # Retry button (hidden until error)
        self.retry_btn = ctk.CTkButton(
            self, text="Retry", command=self._retry,
            width=140, state="disabled"
        )
        self.retry_btn.pack(pady=8)

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

    def _start_polling(self):
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        import time
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
                self.after(0, self._on_error, str(e))
                return
            time.sleep(2)

    def _try_connect(self):
        if self.app.mock_path:
            from src.device.mock_device import MockDevice
            device = MockDevice(self.app.mock_path)
            device.connect()
            return device
        # Real iPhone — try pymobiledevice3
        from src.device.iphone_device import iPhoneDevice
        device = iPhoneDevice()
        device.connect()
        return device

    def _on_connected(self, device):
        self._polling = False
        self.app.device = device
        info = device.device_info()
        self.spinner.stop()
        self.spinner.pack_forget()
        self.retry_btn.configure(state="disabled")
        self.status_label.configure(
            text=f"Connected: {info['model']}",
            text_color="#4CAF50"
        )
        self.detail_label.configure(
            text=f"iOS {info['ios_version']}  •  {info['total_count']:,} photos & videos"
        )
        # If resuming, jump to progress screen after brief delay
        if self.resume_session and self.app.resume_session:
            self.after(1200, lambda: self.app.show_screen("progress"))
        else:
            self.after(1200, lambda: self.app.show_screen("destination"))

    def _on_error(self, msg: str):
        self._polling = False
        self.spinner.stop()
        self.spinner.pack_forget()
        self.status_label.configure(text="Connection Failed", text_color="#F44336")
        self.detail_label.configure(
            text=f"{msg}\n\nMake sure iPhone is unlocked, trusted, and the cable is secure.",
            text_color="gray70"
        )
        self.retry_btn.configure(state="normal")

    def _retry(self):
        self.detail_label.configure(text="", text_color="gray60")
        self.status_label.configure(text="Plug in your iPhone via USB", text_color="white")
        self.sudo_frame.pack_forget()
        self.spinner.pack(pady=16)
        self.spinner.start()
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
        super().destroy()


class NeedsTunnelError(Exception):
    """Raised when iOS 17+ requires the QUIC tunnel before connection."""
    pass
