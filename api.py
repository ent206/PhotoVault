# api.py
"""
PhotoVault Python API — exposed to the React frontend via PyWebView's js_api.

All public methods are callable from window.pywebview.api.* in JavaScript.
Every method returns a plain JSON-safe dict: {"ok": True, ...} or {"ok": False, "error": "..."}.
Long-running operations fire progress events back via _push() → window.__pv().
"""

import json
import subprocess
import threading
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from src import config
from src.models import PhotoAsset
from src.session_log import SessionLog
from src.transfer_engine import TransferEngine, TransferOptions, TransferProgress
from src.utils.disk_utils import list_drives, check_space, human_size


# ------------------------------------------------------------------ #
# Serialization helpers (module-level, pure functions)                #
# ------------------------------------------------------------------ #

def _serialize_asset(asset: PhotoAsset) -> dict:
    return {
        "id": asset.source_path,
        "filename": asset.filename,
        "source_path": asset.source_path,
        "date_taken": asset.date_taken.isoformat(),
        "file_size": asset.file_size,
        "media_type": asset.media_type,
        "live_photo_pair_id": asset.live_photo_pair_id,
        "is_icloud_stub": asset.is_icloud_stub,
        "is_screenshot": asset.is_screenshot,
    }


def _serialize_asset_list(assets: List[PhotoAsset]) -> dict:
    photos = sum(1 for a in assets if a.media_type in ("photo", "live_photo_image"))
    videos = sum(1 for a in assets if a.media_type in ("video", "live_photo_video"))
    screenshots = sum(1 for a in assets if a.is_screenshot)
    total_bytes = sum(a.file_size for a in assets)
    stubs = sum(1 for a in assets if a.is_icloud_stub)
    return {
        "count": len(assets),
        "photos": photos,
        "videos": videos,
        "screenshots": screenshots,
        "total_bytes": total_bytes,
        "total_size_human": human_size(total_bytes) if total_bytes > 0 else "size unavailable",
        "stubs": stubs,
        "assets": [_serialize_asset(a) for a in assets],
    }


def _serialize_progress(p: TransferProgress) -> dict:
    pct = p.files_done / p.files_total if p.files_total else 0
    return {
        "current_filename": p.current_filename,
        "files_done": p.files_done,
        "files_total": p.files_total,
        "bytes_done": p.bytes_done,
        "bytes_total": p.bytes_total,
        "pct": round(pct, 4),
        "speed_mbps": round(p.speed_mbps, 2),
        "eta_seconds": round(p.eta_seconds),
    }


def _dest_path_for(dest: Path, asset: PhotoAsset) -> Path:
    """Mirrors TransferEngine._dest_path_for() exactly."""
    month_folder = asset.date_taken.strftime("%m - %B")  # e.g. "03 - March"
    year = str(asset.date_taken.year)
    return dest / year / month_folder / asset.filename


# ------------------------------------------------------------------ #
# Main API class                                                       #
# ------------------------------------------------------------------ #

class PhotoVaultAPI:
    """Exposed to JS via webview.create_window(js_api=api)."""

    PROGRESS_INTERVAL = 0.20  # seconds between throttled transfer:progress pushes

    def __init__(self, session_log: SessionLog, mock_path: Optional[Path] = None):
        self._session_log = session_log
        self._mock_path = mock_path
        self._window = None  # set via set_window() after window is created

        self._device = None
        self._device_lock = threading.Lock()

        # source_path → PhotoAsset; populated after scan completes
        self._asset_registry: Dict[str, PhotoAsset] = {}

        self._connect_thread: Optional[threading.Thread] = None
        self._scan_thread: Optional[threading.Thread] = None
        self._transfer_thread: Optional[threading.Thread] = None
        self._delete_thread: Optional[threading.Thread] = None
        self._ping_thread: Optional[threading.Thread] = None

        # Tracks consecutive session-conflict failures across poll cycles
        self._connect_failures = 0

        self._engine: Optional[TransferEngine] = None
        self._transfer_active = threading.Event()

        # Throttle state for transfer:progress
        self._last_progress_push = 0.0
        self._latest_progress: Optional[TransferProgress] = None
        self._progress_lock = threading.Lock()

    def set_window(self, window) -> None:
        """Called from main.py after window creation. Not exposed to JS."""
        self._window = window

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _push(self, event: str, data: dict) -> None:
        """Push an event to React. Safe to call from any thread."""
        if self._window is None:
            return
        payload = json.dumps({"event": event, "data": data})
        self._window.evaluate_js(f'window.__pv({payload})')

    @staticmethod
    def _ok(**kwargs) -> dict:
        return {"ok": True, **kwargs}

    @staticmethod
    def _err(e) -> dict:
        return {"ok": False, "error": str(e)}

    def _asset_from_id(self, asset_id: str) -> PhotoAsset:
        asset = self._asset_registry.get(asset_id)
        if asset is None:
            raise KeyError(f"Unknown asset id: {asset_id!r}")
        return asset

    def _assets_from_ids(self, asset_ids: List[str]) -> List[PhotoAsset]:
        missing = [aid for aid in asset_ids if aid not in self._asset_registry]
        if missing:
            raise KeyError(f"Unknown asset ids: {missing[:5]}")
        return [self._asset_registry[aid] for aid in asset_ids]

    # ------------------------------------------------------------------ #
    # Screen 1 — Device connection                                         #
    # ------------------------------------------------------------------ #

    def connect_device(self) -> dict:
        """
        Kick off a background connection attempt. Returns immediately.
        Fires: device:connecting → device:connected | device:error | device:needs_tunnel
        """
        if self._connect_thread and self._connect_thread.is_alive():
            return self._ok(status="already_connecting")
        # Don't re-connect if a device is already registered
        with self._device_lock:
            if self._device is not None:
                return self._ok(status="already_connected")
        self._connect_thread = threading.Thread(
            target=self._connect_worker, daemon=True
        )
        self._connect_thread.start()
        return self._ok(status="connecting")

    # Keywords in the exception message that mean "phone simply isn't plugged in"
    _NO_DEVICE_HINTS = (
        "no device", "nodevice", "devicenotfound", "not found",
        "unable to find", "no iphone", "connection refused",
        "nodeviceconnectederror",  # pymobiledevice3 class name
    )

    # Transient errors that should be retried silently before surfacing to the UI.
    # ConnectionTerminatedError is common when the app restarts with the phone already
    # plugged in — the previous usbmuxd session needs a moment to reset. NOT a trust issue.
    _TRANSIENT_HINTS = ("connectionterminated", "connection terminated", "ssl", "timeout",
                        "connection reset", "broken pipe")

    def _connect_worker(self) -> None:
        # do NOT push device:connecting yet — we don't know if a phone is present.
        # Retry transient errors silently so a phone already plugged in at launch
        # connects cleanly without a brief error flash.
        # iPhoneDevice.connect() owns the retry logic for transient errors.
        # Each iPhoneDevice creates its own asyncio event loop — create it once.
        if self._mock_path:
            from src.device.mock_device import MockDevice
            device = MockDevice(self._mock_path)
        else:
            from src.device.iphone_device import iPhoneDevice
            device = iPhoneDevice()

        try:
            device.connect()
        except Exception as e:
            import traceback, sys
            print(f"[DEBUG] Connection error: {e}", file=sys.stderr)
            traceback.print_exc()
            # Stop the event loop so leaked lockdown sockets are released.
            # Without this, each failed poll accumulates zombie event-loop
            # threads that each hold an open USB lockdown socket — which
            # eventually causes our OWN code to cause "session conflict".
            if not self._mock_path:
                try:
                    device.close()
                except Exception:
                    pass
            err = str(e)
            err_lower = err.lower()
            if any(k in err_lower for k in ("tunnel", "quic", "remotepairing", "remotexpc")):
                self._push("device:connecting", {})
                self._push("device:needs_tunnel", {"message": err})
            elif any(k in err_lower for k in self._NO_DEVICE_HINTS):
                self._connect_failures = 0
                # Phone is physically absent — ensure UI clears any lingering error
                self._push("device:disconnected", {})
            elif "nopairingrecord" in err_lower:
                self._connect_failures = 0
                self._push("device:error", {
                    "message": "Tap \"Trust\" on your iPhone when prompted, then try again."
                })
            elif "sessionconflict" in err_lower:
                self._connect_failures += 1
                if self._connect_failures >= 7:
                    # ~14 s of sustained conflict.
                    # Could be: (a) another app holds the lockdown session, or
                    # (b) our pairing record is stale after a macOS re-trust.
                    # Delete the stale plist so the next attempt forces fresh
                    # pairing — if the phone needs Trust it will prompt again,
                    # which is the correct recovery path.
                    self._delete_stale_plist()
                    self._connect_failures = 0  # reset so next cycle is quiet
                    self._push("device:error", {
                        "message": "Tap \"Trust\" on your iPhone if prompted — or close Finder/Apple Devices and unplug/replug."
                    })
                else:
                    # Still within grace period — show "Connecting…" so poll retries
                    self._push("device:connecting", {})
            elif "invalidhostid" in err_lower:
                # The Mac's HostID changed (e.g., after macOS update or network change).
                # Treat same as NoPairingRecord — user needs to re-trust.
                self._connect_failures = 0
                self._push("device:error", {
                    "message": "Tap \"Trust\" on your iPhone when prompted, then try again."
                })
            elif any(k in err_lower for k in ("pairingerror", "password protected")):
                self._push("device:error", {
                    "message": "Tap \"Trust\" on your iPhone when prompted, then try again."
                })
            elif "pairingpending" in err_lower:
                self._push("device:error", {
                    "message": "Please tap \"Trust\" on your iPhone, then click Retry Connection."
                })
            else:
                import re
                clean = re.sub(r"^\[.*?\]\s*", "", err)
                self._push("device:error", {"message": clean})
            return

        self._connect_failures = 0
        with self._device_lock:
            self._device = device
            self._asset_registry = {}

        info = device.device_info()
        self._push("device:connected", {
            "model": info.get("model", "iPhone"),
            "ios_version": info.get("ios_version", ""),
            "total_count": info.get("total_count", 0),
        })
        self._start_ping_monitor()

    def _delete_stale_plist(self) -> None:
        """Remove stale pymobiledevice3 pairing plists.

        After macOS re-establishes trust with the phone (e.g. user taps Trust),
        our copy at ~/.pymobiledevice3/<udid>.plist is outdated.  Deleting it
        forces the next create_using_usbmux(autopair=True) to generate a fresh
        plist with the correct keys.
        """
        try:
            pdir = Path.home() / ".pymobiledevice3"
            for p in pdir.glob("*.plist"):
                try:
                    p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def start_tunnel(self, password: str) -> dict:
        """
        Launch the iOS 17+ QUIC tunnel subprocess with sudo password.
        Returns immediately; the tunnel process runs detached.
        """
        try:
            proc = subprocess.Popen(
                ["sudo", "-S", "python3", "-m",
                 "pymobiledevice3", "remote", "start-quic-tunnel"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            proc.stdin.write((password + "\n").encode())
            proc.stdin.flush()
            self._push("tunnel:started", {})
            return self._ok()
        except Exception as e:
            return self._err(e)

    def _start_ping_monitor(self) -> None:
        self._ping_thread = threading.Thread(
            target=self._ping_worker, daemon=True
        )
        self._ping_thread.start()

    def _ping_worker(self) -> None:
        consecutive_failures = 0
        while True:
            time.sleep(2)  # Faster polling for quicker disconnect detection
            with self._device_lock:
                device = self._device
            if device is None:
                return
            try:
                alive = device.ping()
            except Exception:
                alive = False
            if not alive:
                consecutive_failures += 1
                if consecutive_failures < 3:
                    continue  # require 3 consecutive failures before declaring disconnect (6s total)
            else:
                consecutive_failures = 0
                continue
            with self._device_lock:
                disconnected_device = self._device
                self._device = None
                self._asset_registry = {}
            self._connect_failures = 0
            if disconnected_device is not None and not self._mock_path:
                try:
                    disconnected_device.close()
                except Exception:
                    pass
            self._push("device:disconnected", {})
            return

    # ------------------------------------------------------------------ #
    # Screen 2 — Destination                                               #
    # ------------------------------------------------------------------ #

    def list_drives(self) -> dict:
        """Synchronous. Returns connected drives + recent destinations."""
        try:
            drives = [
                {
                    "name": d.name,
                    "path": str(d.path),
                    "free_bytes": d.free_bytes,
                    "total_bytes": d.total_bytes,
                    "free_human": human_size(d.free_bytes),
                    "total_human": human_size(d.total_bytes),
                    "is_external": d.is_external,
                }
                for d in list_drives()
            ]
            recents = [
                p for p in config.get_recent_destinations()
                if Path(p).exists()
            ]
            return self._ok(drives=drives, recent_destinations=recents)
        except Exception as e:
            return self._err(e)

    def browse_folder(self) -> dict:
        """Open a native folder-picker dialog. Returns chosen path or null."""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                allow_multiple=False,
            )
            chosen = result[0] if result else None
            return self._ok(path=chosen)
        except Exception as e:
            return self._err(e)

    def set_destination(self, path: str, subfolder: str = "") -> dict:
        """Validate, create, and persist the chosen destination."""
        try:
            dest = Path(path)
            if subfolder.strip():
                dest = dest / subfolder.strip()
            dest.mkdir(parents=True, exist_ok=True)
            config.set_last_destination(str(dest))
            return self._ok(resolved_path=str(dest))
        except Exception as e:
            return self._err(e)

    def check_space(self, path: str, required_bytes: int) -> dict:
        """Synchronous disk space check."""
        try:
            result = check_space(Path(path), required_bytes)
            result["free_human"] = human_size(result["free"])
            return self._ok(**result)
        except Exception as e:
            return self._err(e)

    # ------------------------------------------------------------------ #
    # Screen 3 — Date range & scan                                         #
    # ------------------------------------------------------------------ #

    def get_saved_date_range(self) -> dict:
        """Synchronous. Returns last-used date range from settings."""
        try:
            last = config.get_last_date_range()
            if last:
                return self._ok(start=last[0], end=last[1])
            return self._ok(start=None, end=None)
        except Exception as e:
            return self._err(e)

    def start_scan(self, start_iso: str, end_iso: str) -> dict:
        """
        Kick off a device scan in background. Returns immediately.
        Fires: scan:db_progress | scan:progress → scan:complete | scan:error
        """
        if self._scan_thread and self._scan_thread.is_alive():
            return self._ok(status="already_scanning")

        with self._device_lock:
            device = self._device
        if device is None:
            return self._err("No device connected")

        try:
            start_dt = datetime.combine(date.fromisoformat(start_iso), datetime.min.time())
            end_dt = datetime.combine(date.fromisoformat(end_iso), datetime.max.time())
        except ValueError as e:
            return self._err(e)

        config.set_last_date_range(start_iso, end_iso)
        device.reset_scan()

        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(device, start_dt, end_dt),
            daemon=True,
        )
        self._scan_thread.start()
        return self._ok(status="scanning")

    def _scan_worker(self, device, start_dt: datetime, end_dt: datetime) -> None:
        def on_progress(current: int, total: int):
            self._push("scan:progress", {
                "current": current,
                "total": total,
                "pct": current / total if total else 0,
            })

        def on_db_progress(read: int, total: int, elapsed: float):
            pct = read / total if total > 0 else 0
            speed = read / elapsed if elapsed > 0.5 and read > 0 else 0
            eta = int((total - read) / speed) if speed > 0 else None
            self._push("scan:db_progress", {
                "read_bytes": read,
                "total_bytes": total,
                "pct": pct,
                "read_mb": round(read / 1_048_576, 1),
                "total_mb": round(total / 1_048_576, 1),
                "eta_seconds": eta,
            })

        try:
            device.scan(
                on_progress=on_progress,
                on_db_progress=on_db_progress,
                start_date=start_dt,
                end_date=end_dt,
            )
        except Exception as e:
            self._push("scan:error", {"message": str(e)})
            return

        assets = device.list_assets(start_dt, end_dt)
        with self._device_lock:
            self._asset_registry = {a.source_path: a for a in assets}

        self._push("scan:complete", _serialize_asset_list(assets))

    def list_assets(self, start_iso: str, end_iso: str) -> dict:
        """
        Synchronous filter over already-scanned assets (no re-scan).
        Used for live preview after scan completes.
        """
        try:
            start_dt = datetime.combine(date.fromisoformat(start_iso), datetime.min.time())
            end_dt = datetime.combine(date.fromisoformat(end_iso), datetime.max.time())
            with self._device_lock:
                device = self._device
            if device is None:
                return self._err("No device connected")
            assets = device.list_assets(start_dt, end_dt)
            return self._ok(**_serialize_asset_list(assets))
        except Exception as e:
            return self._err(e)

    # ------------------------------------------------------------------ #
    # Screen 4 — Transfer summary                                          #
    # ------------------------------------------------------------------ #

    def get_transfer_summary(self, asset_ids: List[str], destination: str) -> dict:
        """
        Synchronous pre-flight: duplicate count, space check, ETA estimate.
        """
        try:
            assets = self._assets_from_ids(asset_ids)
            dest = Path(destination)
            total_bytes = sum(a.file_size for a in assets)
            photos = sum(1 for a in assets if a.media_type in ("photo", "live_photo_image"))
            videos = sum(1 for a in assets if a.media_type in ("video", "live_photo_video"))
            stubs = sum(1 for a in assets if a.is_icloud_stub)
            duplicates = sum(
                1 for a in assets
                if _dest_path_for(dest, a).exists()
                and _dest_path_for(dest, a).stat().st_size == a.file_size
            )
            space = check_space(dest, total_bytes)
            eta_secs = (total_bytes / 1_048_576) / 35 if total_bytes else 0
            return self._ok(
                photos=photos,
                videos=videos,
                total_bytes=total_bytes,
                total_size_human=human_size(total_bytes) if total_bytes > 0 else "size unavailable",
                duplicates=duplicates,
                stubs=stubs,
                space_ok=space["ok"],
                free_bytes=space["free"],
                free_human=human_size(space["free"]),
                headroom_pct=space["headroom_pct"],
                eta_seconds=round(eta_secs),
            )
        except Exception as e:
            return self._err(e)

    # ------------------------------------------------------------------ #
    # Screen 5 — Transfer                                                  #
    # ------------------------------------------------------------------ #

    def start_transfer(
        self,
        asset_ids: List[str],
        destination: str,
        safe_mode: bool = True,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Kick off transfer in background. Returns immediately.
        Fires: transfer:progress (throttled) | transfer:sleeping | transfer:resumed
               → transfer:complete | transfer:error
        """
        if self._transfer_active.is_set():
            return self._err("A transfer is already running")

        with self._device_lock:
            device = self._device
        if device is None:
            return self._err("No device connected")

        try:
            assets = self._assets_from_ids(asset_ids)
        except KeyError as e:
            return self._err(e)

        options = TransferOptions(
            safe_mode=safe_mode,
            session_id=session_id or str(uuid.uuid4()),
        )

        self._last_progress_push = 0.0
        self._latest_progress = None

        self._engine = TransferEngine(
            device=device,
            destination=Path(destination),
            session_log=self._session_log,
            options=options,
            on_progress=self._on_transfer_progress,
            on_device_sleeping=self._on_device_sleeping,
            on_device_resumed=self._on_device_resumed,
        )

        self._transfer_active.set()
        self._transfer_thread = threading.Thread(
            target=self._transfer_worker,
            args=(assets,),
            daemon=True,
        )
        self._transfer_thread.start()
        return self._ok(session_id=options.session_id)

    def _transfer_worker(self, assets: List[PhotoAsset]) -> None:
        try:
            results = self._engine.transfer(assets)
            self._flush_progress()
            self._push("transfer:complete", {
                "completed": results["completed"],
                "skipped": results["skipped"],
                "failed": results["failed"],
                "failed_files": results["failed_files"],
            })
        except Exception as e:
            self._flush_progress()
            self._push("transfer:error", {"message": str(e)})
        finally:
            self._transfer_active.clear()
            self._engine = None

    def _on_transfer_progress(self, p: TransferProgress) -> None:
        """Called from transfer thread. Throttled to ~5 Hz."""
        with self._progress_lock:
            self._latest_progress = p
            now = time.monotonic()
            if now - self._last_progress_push >= self.PROGRESS_INTERVAL:
                self._last_progress_push = now
                snapshot = _serialize_progress(p)
            else:
                return
        self._push("transfer:progress", snapshot)

    def _flush_progress(self) -> None:
        """Force-push the most recent progress before transfer:complete."""
        with self._progress_lock:
            p = self._latest_progress
        if p is not None:
            self._push("transfer:progress", _serialize_progress(p))

    def _on_device_sleeping(self, retry_in: int) -> None:
        self._push("transfer:sleeping", {"retry_in_seconds": retry_in})

    def _on_device_resumed(self) -> None:
        self._push("transfer:resumed", {})

    def pause_transfer(self) -> dict:
        engine = self._engine
        if engine is None:
            return self._err("No active transfer")
        engine.pause()
        self._push("transfer:paused", {})
        return self._ok()

    def resume_transfer(self) -> dict:
        engine = self._engine
        if engine is None:
            return self._err("No active transfer")
        engine.resume_pause()
        self._push("transfer:resumed_user", {})
        return self._ok()

    def cancel_transfer(self) -> dict:
        engine = self._engine
        if engine is None:
            return self._err("No active transfer")
        engine.cancel()
        self._push("transfer:cancelled", {})
        return self._ok()

    # ------------------------------------------------------------------ #
    # Screen 6 — Complete / Resume sessions                                #
    # ------------------------------------------------------------------ #

    def get_incomplete_sessions(self) -> dict:
        """Synchronous. Returns sessions from the last 7 days that can be resumed."""
        try:
            sessions = self._session_log.find_incomplete()
            return self._ok(sessions=[
                {
                    "session_id": s.session_id,
                    "started_at": s.started_at.isoformat(),
                    "source_device": s.source_device,
                    "destination_path": s.destination_path,
                    "completed_count": s.completed_count,
                    "total_files": s.total_files,
                }
                for s in sessions
            ])
        except Exception as e:
            return self._err(e)

    def dismiss_session(self, session_id: str) -> dict:
        """Mark a session dismissed so it never resurfaces."""
        try:
            self._session_log.dismiss(session_id)
            return self._ok()
        except Exception as e:
            return self._err(e)

    # ------------------------------------------------------------------ #
    # Post-transfer delete                                                 #
    # ------------------------------------------------------------------ #

    def start_delete(self, asset_ids: List[str], destination: str) -> dict:
        """
        Delete files from device after verifying destination copy.
        Fires: delete:progress → delete:complete | delete:error
        """
        if self._delete_thread and self._delete_thread.is_alive():
            return self._err("A deletion is already running")

        with self._device_lock:
            device = self._device
        if device is None:
            return self._err("No device connected")

        try:
            assets = self._assets_from_ids(asset_ids)
        except KeyError as e:
            return self._err(e)

        self._delete_thread = threading.Thread(
            target=self._delete_worker,
            args=(assets, Path(destination), device),
            daemon=True,
        )
        self._delete_thread.start()
        return self._ok(total=len(assets))

    def _delete_worker(self, assets: List[PhotoAsset], dest: Path, device) -> None:
        deleted = 0
        failed = 0
        freed_bytes = 0
        total = len(assets)

        for i, asset in enumerate(assets):
            dest_path = _dest_path_for(dest, asset)
            # Pre-verify: destination copy must exist and size must match
            if not dest_path.exists() or dest_path.stat().st_size != asset.file_size:
                failed += 1
            else:
                try:
                    device.delete_file(asset)
                    deleted += 1
                    freed_bytes += asset.file_size
                except Exception:
                    failed += 1

            self._push("delete:progress", {
                "done": i + 1,
                "total": total,
                "deleted": deleted,
                "failed": failed,
                "freed_bytes": freed_bytes,
                "freed_human": human_size(freed_bytes) if freed_bytes > 0 else "0 B",
                "pct": (i + 1) / total,
            })

        self._push("delete:complete", {
            "deleted": deleted,
            "failed": failed,
            "freed_bytes": freed_bytes,
            "freed_human": human_size(freed_bytes) if freed_bytes > 0 else "0 B",
        })

    # ------------------------------------------------------------------ #
    # Settings                                                             #
    # ------------------------------------------------------------------ #

    def get_settings(self) -> dict:
        """Synchronous. Returns all persisted user settings."""
        try:
            return self._ok(
                last_destination=config.get_last_destination(),
                recent_destinations=config.get_recent_destinations(),
                last_date_range=config.get_last_date_range(),
            )
        except Exception as e:
            return self._err(e)
