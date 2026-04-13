# src/device/iphone_device.py
"""
Real iPhone device implementation using pymobiledevice3 (v9.x async API).

Requires:
- iPhone connected via USB and trusted
- For iOS 17+: tunnel service running (started from Screen 1 or manually)
  sudo python3 -m pymobiledevice3 remote start-quic-tunnel

Scan strategy:
  1. Fast path: read /PhotoData/Photos.sqlite via AFC and query for assets
     in the requested date range.  The Photos database stores the EXIF
     capture date (same value the Photos app shows), so results are
     accurate for imported/migrated photos.  Typical time: 5-30 seconds
     regardless of library size.

  2. Fallback (if DB unreadable): read EXIF from the first chunk of each
     DCIM file.  Slower (seconds per file) but still correct.

  st_birthtime is NOT used for date filtering — it reflects when a file
  was copied to THIS device, not when the photo was taken.
"""
import asyncio
import os
import sqlite3
import struct
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.device.base import DeviceInterface
from src.models import PhotoAsset

MEDIA_EXTS = {".jpg", ".jpeg", ".heic", ".png", ".mov", ".mp4", ".m4v"}
LIVE_PHOTO_VIDEO_EXTS = {".mov"}

# Core Data epoch: seconds between 1970-01-01 and 2001-01-01
_COREDATA_OFFSET = 978_307_200

# How many bytes to read for EXIF extraction (fallback path only)
_JPEG_READ = 65_536       # 64 KB
_HEIC_READ = 524_288      # 512 KB
_VIDEO_READ = 65_536      # 64 KB


class iPhoneDevice(DeviceInterface):
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

        self._lockdown = None
        self._afc = None
        self._assets: Optional[List[PhotoAsset]] = None
        self._info: Optional[Dict] = None

    # ------------------------------------------------------------------ #
    # Internal async runner                                                #
    # ------------------------------------------------------------------ #

    def _run(self, coro, timeout: int = 120):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------ #
    # DeviceInterface implementation                                       #
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        """
        Establish lockdown + AFC connection.

        Strategy:
          1. list_devices() — fast usbmuxd check (no SSL). Fail immediately if
             no phone is physically connected; no point attempting lockdown.
          2. autopair selection — autopair=False when a plist already exists
             (prevents spurious "Trust" dialogs during macOS session conflicts);
             autopair=True when no plist exists (sends Pair so the phone shows
             the Trust dialog and we get a fresh plist).
          3. Check lockdown.paired — if False after a successful call it means the
             SSL session wasn't established (session conflict). Treat as transient,
             retry with 2 s gap.
          4. Up to 2 retries (1 s window) — fast fail so the caller can retry
             immediately via the 2 s poll. Session conflicts clear quickly.
          5. If all retries fail, check whether a pairing record exists to give the
             user the right message (re-pair vs session conflict).
        """
        import time as _time
        from pathlib import Path
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.usbmux import list_devices
        from pymobiledevice3.exceptions import (
            ConnectionTerminatedError,
            NoDeviceConnectedError,
            DeviceNotFoundError,
            BadDevError,
        )

        # ── Step 1: fast presence check ──────────────────────────────────
        # Retry a few times - device may take a moment to enumerate after app launch
        devices = []
        for _ in range(3):
            try:
                devices = self._run(list_devices(), timeout=3)
            except Exception:
                devices = []
            if devices:
                break
            _time.sleep(0.3)

        import sys
        print(f"[DEBUG] list_devices returned: {devices}", file=sys.stderr)
        for d in devices:
            print(f"[DEBUG]   - serial={getattr(d, 'serial', '?')}, conn_type={getattr(d, 'conn_type', '?')}, version={getattr(d, 'version', '?')}", file=sys.stderr)

        if not devices:
            self._lockdown = None
            self._afc = None
            raise ConnectionError("No device found")

        # ── Step 2-4: attempt lockdown with retries ───────────────────────
        last_exc: Optional[Exception] = None

        # Strategy:
        # 1. If local pairing exists -> use autopair=False (trusted connection)
        # 2. If no pairing exists -> use autopair=True (trigger Trust dialog)
        # 3. If only system pairing exists -> try autopair=False first, but if
        #    connection fails with ConnectionTerminatedError, switch to
        #    autopair=True to create a fresh local pairing (system record may be stale)
        #
        # IMPORTANT: Prefer USB devices over Network devices to avoid WiFi issues
        usb_devices = [d for d in devices if getattr(d, 'connection_type', '') == 'USB']
        target_device = usb_devices[0] if usb_devices else devices[0]
        udid = target_device.serial if target_device else ""
        print(f"[DEBUG] Selected device: udid={udid}, connection_type={getattr(target_device, 'connection_type', '?')}", file=sys.stderr)
        pair_record_path = Path.home() / ".pymobiledevice3" / f"{udid}.plist"
        system_pair_record_path = Path(f"/var/db/lockdown/{udid}.plist")
        local_plist_exists = pair_record_path.exists()
        system_plist_exists = system_pair_record_path.exists()

        # Start with autopair=False if any pairing record exists
        use_autopair = not (local_plist_exists or system_plist_exists)
        # Track if we should try autopair=True as fallback (system-only pairing)
        try_autopair_fallback = system_plist_exists and not local_plist_exists

        import sys
        print(f"[DEBUG] udid={udid}, local_plist={local_plist_exists}, system_plist={system_plist_exists}, use_autopair={use_autopair}, fallback={try_autopair_fallback}", file=sys.stderr)

        def _close_lockdown(ld):
            """Best-effort close of a LockdownClient socket."""
            try:
                aclose = getattr(ld, "aclose", None)
                if aclose is not None:
                    self._run(aclose(), timeout=2)
            except Exception:
                pass

        for attempt in range(4):  # Up to 4 attempts
            lockdown = None
            try:
                import sys
                print(f"[DEBUG] Attempt {attempt}: calling create_using_usbmux(autopair={use_autopair})", file=sys.stderr)
                lockdown = self._run(create_using_usbmux(autopair=use_autopair))
                print(f"[DEBUG] Attempt {attempt}: lockdown created, paired={lockdown.paired}, service={getattr(lockdown, '_service', None)}", file=sys.stderr)

                if not lockdown.paired:
                    # validate_pairing() returned False — pairing record is stale
                    _close_lockdown(lockdown)
                    lockdown = None
                    last_exc = ConnectionError(
                        f"[ConnectionTerminatedError] session not established"
                    )
                    # If we only had system pairing, try autopair=True to trigger Trust dialog
                    if try_autopair_fallback and not use_autopair and attempt < 3:
                        print(f"[DEBUG] Switching to autopair=True to trigger Trust dialog", file=sys.stderr)
                        use_autopair = True
                        _time.sleep(0.3)
                        continue
                    if attempt < 3:
                        _time.sleep(0.5)
                        continue
                    break

                self._lockdown = lockdown
                last_exc = None
                break

            except (NoDeviceConnectedError, DeviceNotFoundError, BadDevError):
                if lockdown is not None:
                    _close_lockdown(lockdown)
                # Device was enumerated but now disappeared - could be transient
                last_exc = ConnectionError("Device disconnected during connection")
                if attempt < 3:
                    _time.sleep(0.5)
                    continue
                self._lockdown = None
                self._afc = None
                raise ConnectionError("No device found") from None

            except ConnectionTerminatedError as e:
                if lockdown is not None:
                    _close_lockdown(lockdown)
                import sys
                print(f"[DEBUG] Attempt {attempt}: ConnectionTerminatedError", file=sys.stderr)
                last_exc = e
                # If we only had system pairing and haven't tried autopair yet, switch to it
                if try_autopair_fallback and not use_autopair and attempt < 3:
                    print(f"[DEBUG] Connection terminated with system pairing only - switching to autopair=True", file=sys.stderr)
                    use_autopair = True
                    _time.sleep(0.3)
                    continue
                if attempt < 3:
                    _time.sleep(0.5)
                    continue
                break

            except Exception as e:
                if lockdown is not None:
                    _close_lockdown(lockdown)
                import sys
                print(f"[DEBUG] Attempt {attempt} exception: {type(e).__name__}: {e}", file=sys.stderr)
                err_lower = str(e).lower()
                if any(k in err_lower for k in ("tunnel", "quic", "remotepairing", "remotexpc")):
                    self._lockdown = None
                    self._afc = None
                    from src.gui.screen1_connect import NeedsTunnelError
                    raise NeedsTunnelError(str(e)) from e

                last_exc = e
                if attempt < 3:
                    _time.sleep(0.5)
                    continue
                break

        if last_exc is not None:
            self._lockdown = None
            self._afc = None
            # Re-check if plist was created during the attempt (user tapped Trust)
            # Also wait briefly for iOS to finish writing the pairing record
            for _ in range(5):
                local_plist_exists = pair_record_path.exists()
                system_plist_exists = system_pair_record_path.exists()
                if local_plist_exists:
                    break
                _time.sleep(0.2)
            import sys
            print(f"[DEBUG] Final error: {last_exc}, local_plist={local_plist_exists}, system_plist={system_plist_exists}", file=sys.stderr)

            # If a local plist appeared during the attempt, try once more with autopair=False
            if local_plist_exists:
                try:
                    print(f"[DEBUG] Local plist now exists, retrying with autopair=False", file=sys.stderr)
                    lockdown = self._run(create_using_usbmux(autopair=False))
                    if lockdown.paired:
                        self._lockdown = lockdown
                        self._afc = self._run(self._create_afc())
                        self._info = self._fetch_device_info()
                        self._assets = None
                        return  # Success!
                except Exception as retry_e:
                    print(f"[DEBUG] Retry with new plist failed: {retry_e}", file=sys.stderr)
                    last_exc = retry_e

            # Check if this is a stale system pairing issue
            # This happens when the system has a pairing record but the iPhone
            # doesn't trust it anymore - requires unplug/replug OR deletion of stale plist
            has_stale_system_pairing = (
                system_plist_exists and
                not local_plist_exists and
                isinstance(last_exc, Exception) and
                type(last_exc).__name__ == "ConnectionTerminatedError"
            )

            if has_stale_system_pairing:
                # The system has a pairing record but iPhone rejects it.
                # Solution: Use Python API to force a fresh pairing
                # CLI commands don't work because they also can't connect

                try:
                    if pair_record_path.exists():
                        pair_record_path.unlink()
                        print(f"[DEBUG] Deleted local pairing plist", file=sys.stderr)
                except Exception:
                    pass

                # Solution: Bypass system pairing by setting pair_record to empty dict
                # This forces pymobiledevice3 to create a fresh local pairing
                try:
                    from pymobiledevice3.exceptions import PairingDialogResponsePendingError

                    print(f"[DEBUG] Attempting fresh pair with empty pair_record", file=sys.stderr)

                    # Create with pair_record={} to force fresh pairing
                    # pair_record=None causes fetch_pair_record() to search system pairing
                    # pair_record={} prevents that and forces a new Pair command
                    ld = self._run(create_using_usbmux(
                        serial=udid,
                        autopair=True,
                        pair_timeout=30,
                        pair_record={}  # Force fresh pairing, bypass system records
                    ))
                    print(f"[DEBUG] LockdownClient created, paired={ld.paired}", file=sys.stderr)

                    if ld.paired:
                        print(f"[DEBUG] Successfully paired!", file=sys.stderr)
                        self._lockdown = ld
                        self._afc = self._run(self._create_afc())
                        self._info = self._fetch_device_info()
                        self._assets = None
                        return  # Success!

                except PairingDialogResponsePendingError:
                    print(f"[DEBUG] Pairing dialog pending - user needs to tap Trust", file=sys.stderr)
                    raise ConnectionError(
                        "[PairingPending] Please tap 'Trust' on your iPhone, then click Retry Connection."
                    )
                except Exception as retry_e:
                    import traceback
                    print(f"[DEBUG] Fresh pair failed: {type(retry_e).__name__}: {retry_e}", file=sys.stderr)
                    traceback.print_exc()

                raise ConnectionError(
                    "[StalePairing] The iPhone connection needs to be refreshed. "
                    "Please unplug your iPhone, wait 2 seconds, then plug it back in. "
                    "When the 'Trust This Computer' dialog appears on your iPhone, tap 'Trust'."
                )
            elif local_plist_exists or system_plist_exists:
                raise ConnectionError(
                    "[SessionConflict] iPhone session is held by another process — "
                    "try closing Finder or Apple Devices, then unplug and replug."
                )
            else:
                raise ConnectionError(
                    "[NoPairingRecord] iPhone has not been paired with this Mac — "
                    "unplug, replug, and tap Trust on your iPhone."
                )

        # ── Step 5: create AFC session ────────────────────────────────────
        try:
            self._afc = self._run(self._create_afc())
        except Exception as e:
            self._lockdown = None
            self._afc = None
            raise ConnectionError(
                f"Could not connect to iPhone: [{type(e).__name__}] {e}"
            ) from e

        self._info = self._fetch_device_info()
        self._assets = None  # None = never scanned

    async def _create_afc(self):
        from pymobiledevice3.services.afc import AfcService
        return AfcService(lockdown=self._lockdown)

    def scan(self, on_progress=None, on_db_progress=None,
             start_date: Optional[datetime] = None,
             end_date: Optional[datetime] = None) -> None:
        # AFC connection may have gone stale during screen navigation — reconnect fresh
        self._reconnect()
        self._assets = self._run(
            self._async_scan(on_progress, on_db_progress, start_date, end_date), timeout=1800
        )

    def is_scanned(self) -> bool:
        return self._assets is not None

    def reset_scan(self) -> None:
        self._assets = None

    def ping(self) -> bool:
        """Check if the device is still physically connected.

        Reuses the existing lockdown connection for a lightweight get_value()
        call rather than opening a new USB session, which would conflict with
        the active AFC connection and cause false disconnects.
        """
        try:
            if self._lockdown is None:
                return False
            self._run(self._lockdown.get_value(key="DeviceName"), timeout=5)
            return True
        except Exception:
            return False

    def is_connected(self) -> bool:
        return self._lockdown is not None

    def disconnect(self) -> None:
        self._lockdown = None
        self._afc = None

    def close(self) -> None:
        """Stop the event loop thread and release all USB resources.

        Call this when a connect attempt fails so the asyncio event loop
        (and any open lockdown sockets) are released immediately rather than
        leaking until the next GC cycle.  Safe to call from any thread.
        """
        self._lockdown = None
        self._afc = None
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass

    def device_info(self) -> Dict:
        return self._info

    def list_assets(self, start_date: datetime, end_date: datetime) -> List[PhotoAsset]:
        if self._assets is None:
            return []
        return [a for a in self._assets if start_date <= a.date_taken <= end_date]

    def read_file(self, asset: PhotoAsset) -> bytes:
        for attempt in range(3):
            try:
                return self._run(self._read_file_fresh(asset.source_path))
            except Exception as exc:
                print(f"[read_file attempt {attempt}] {type(exc).__name__}: {exc}")
                if attempt == 2:
                    raise IOError(f"Failed to read {asset.source_path}: {exc}") from exc
                try:
                    self._reconnect()
                except Exception as re:
                    print(f"[reconnect failed] {type(re).__name__}: {re}")

    async def _read_file_fresh(self, path: str) -> bytes:
        """Open a brand-new AfcService for each file read, closing it cleanly after.

        Reusing an AfcService across many reads causes the underlying socket
        to die. A fresh service per file avoids this. aclose() cancels the
        background reader task so no pending tasks are left behind.
        """
        from pymobiledevice3.services.afc import AfcService
        afc = AfcService(lockdown=self._lockdown)
        try:
            return bytes(await afc.get_file_contents(path))
        finally:
            await afc.aclose()

    def _reconnect(self) -> None:
        """Re-establish lockdown + AFC from scratch (handles SSL drops)."""
        from pymobiledevice3.lockdown import create_using_usbmux
        self._lockdown = self._run(create_using_usbmux())
        self._afc = self._run(self._create_afc())

    def delete_file(self, asset: PhotoAsset) -> None:
        try:
            self._run(self._afc.rm(asset.source_path))
        except Exception as e:
            raise IOError(f"Failed to delete {asset.source_path}: {e}") from e

    # ------------------------------------------------------------------ #
    # Device info                                                          #
    # ------------------------------------------------------------------ #

    def _fetch_device_info(self) -> Dict:
        try:
            ios_version = self._run(self._lockdown.get_value(key="ProductVersion")) or "Unknown"
        except Exception:
            ios_version = "Unknown"
        try:
            model = self._lockdown.display_name
            if not model:
                model = self._run(self._lockdown.get_value(key="DeviceName")) or "iPhone"
        except Exception:
            model = "iPhone"
        return {
            "model": model,
            "ios_version": ios_version,
            "total_count": 0,
            "total_size_bytes": 0,
        }

    # ------------------------------------------------------------------ #
    # Top-level scan dispatcher                                            #
    # ------------------------------------------------------------------ #

    async def _async_scan(self, on_progress=None, on_db_progress=None, start_date=None, end_date=None):
        """Try Photos DB first (fast). Fall back to EXIF scan."""
        try:
            assets = await self._scan_via_photos_db(on_progress, on_db_progress, start_date, end_date)
            if assets is not None:
                if self._info:
                    self._info["total_count"] = len(assets)
                return assets
        except Exception:
            pass  # Fall through to EXIF scan

        # Fallback: read EXIF from individual files
        return await self._async_scan_dcim(on_progress, start_date, end_date)

    # ------------------------------------------------------------------ #
    # Fast path: Photos.sqlite database                                    #
    # ------------------------------------------------------------------ #

    async def _scan_via_photos_db(
        self,
        on_progress=None,
        on_db_progress=None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[List[PhotoAsset]]:
        """Download and query Photos.sqlite. Returns None to signal fallback needed."""

        db_bytes = await self._download_photos_db(on_db_progress)
        if not db_bytes:
            return None

        # Try WAL + SHM for a complete consistent read
        wal_bytes, shm_bytes = await self._download_wal()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "Photos.sqlite")
            with open(db_path, "wb") as f:
                f.write(db_bytes)
            if wal_bytes:
                with open(db_path + "-wal", "wb") as f:
                    f.write(wal_bytes)
                with open(db_path + "-shm", "wb") as f:
                    f.write(shm_bytes or b"")

            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            except Exception:
                conn = sqlite3.connect(db_path)

            try:
                assets = self._query_photos_db(conn, start_date, end_date)
            finally:
                conn.close()

        if on_progress:
            on_progress(1, 1)

        return assets

    async def _download_photos_db(self, on_progress=None) -> Optional[bytes]:
        """Download Photos.sqlite with chunked reads and progress reporting.

        Caches the result in self._db_cache so repeated scans (different date
        ranges in the same session) skip the download entirely.

        on_progress(bytes_read, total_bytes, elapsed_seconds) is called after
        each 4 MB chunk. Falls back to get_file_contents() if open() fails.
        """
        import time
        from pymobiledevice3.services.afc import AfcService

        CHUNK = 4 * 1024 * 1024  # 4 MB per read

        for path in ("/PhotoData/Photos.sqlite", "/PhotoData/database/Photos.sqlite"):
            afc = AfcService(lockdown=self._lockdown)
            try:
                # Get file size for progress calculation
                total = 0
                try:
                    stat = await afc.os_stat(path)
                    total = int(stat.st_size)
                except Exception:
                    pass

                data = None

                # Attempt chunked read (gives real progress)
                try:
                    fh = await afc.open(path, "r")
                    chunks = []
                    read = 0
                    t0 = time.monotonic()
                    while True:
                        chunk = await fh.read(CHUNK)
                        if not chunk:
                            break
                        chunk = bytes(chunk)
                        chunks.append(chunk)
                        read += len(chunk)
                        if on_progress and total > 0:
                            on_progress(read, total, max(time.monotonic() - t0, 0.001))
                    await fh.close()
                    if chunks:
                        data = b''.join(chunks)
                except Exception:
                    pass

                # Fallback: single blocking read (no progress)
                if not data:
                    raw = await afc.get_file_contents(path)
                    data = bytes(raw) if raw else None

                if data and len(data) > 1024:
                    if on_progress and total > 0:
                        on_progress(total, total, 0.0)
                    return data
            except Exception:
                continue
            finally:
                try:
                    await afc.aclose()
                except Exception:
                    pass

        return None

    async def _download_wal(self):
        """Try to download WAL + SHM files via fresh AFC connections."""
        from pymobiledevice3.services.afc import AfcService
        for base in ("/PhotoData/Photos.sqlite", "/PhotoData/database/Photos.sqlite"):
            try:
                afc_wal = AfcService(lockdown=self._lockdown)
                try:
                    wal = bytes(await afc_wal.get_file_contents(base + "-wal"))
                finally:
                    await afc_wal.aclose()
                shm = b""
                try:
                    afc_shm = AfcService(lockdown=self._lockdown)
                    shm = bytes(await afc_shm.get_file_contents(base + "-shm"))
                    await afc_shm.aclose()
                except Exception:
                    pass
                return wal, shm
            except Exception:
                continue
        return None, None

    def _query_photos_db(
        self,
        conn: sqlite3.Connection,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> Optional[List[PhotoAsset]]:
        """Query the Photos SQLite DB for assets in the date range."""
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Find asset table (name varies by iOS version)
        tables = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        if "ZASSET" in tables:
            tbl = "ZASSET"
        elif "ZGENERICASSET" in tables:
            tbl = "ZGENERICASSET"
        else:
            return None  # Unknown schema

        # Inspect available columns
        cols = {r[1] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()}

        size_col    = "ZFILESIZE"    if "ZFILESIZE"    in cols else "NULL"
        kind_col    = "ZKIND"        if "ZKIND"        in cols else "0"
        subtype_col = "ZKINDSUBTYPE" if "ZKINDSUBTYPE" in cols else "0"
        trash_col   = "ZTRASHEDSTATE" if "ZTRASHEDSTATE" in cols else None

        # Build WHERE clause
        params = []
        clauses = []

        if start_date:
            clauses.append("ZDATECREATED >= ?")
            params.append(start_date.timestamp() - _COREDATA_OFFSET)
        if end_date:
            clauses.append("ZDATECREATED <= ?")
            params.append(end_date.timestamp() - _COREDATA_OFFSET)
        if trash_col:
            clauses.append("ZTRASHEDSTATE = 0")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        rows = cur.execute(
            f"SELECT ZDIRECTORY, ZFILENAME, ZDATECREATED, "
            f"{size_col} AS file_size, {kind_col} AS kind, "
            f"{subtype_col} AS kind_subtype "
            f"FROM {tbl} {where} ORDER BY ZDATECREATED",
            params,
        ).fetchall()

        assets: List[PhotoAsset] = []
        # Detect Live Photo pairs: same stem, same directory, image + .mov
        stem_map: Dict[str, Dict] = {}  # (directory, stem) -> {"image": asset, "video": asset}

        for row in rows:
            directory = row["ZDIRECTORY"] or ""
            filename  = row["ZFILENAME"]  or ""
            if not filename:
                continue

            ext = Path(filename).suffix.lower()
            if ext not in MEDIA_EXTS:
                continue

            date_cd = row["ZDATECREATED"]
            if date_cd is None:
                continue
            try:
                date_taken = datetime.fromtimestamp(date_cd + _COREDATA_OFFSET)
            except (OSError, OverflowError, ValueError):
                continue

            file_size = int(row["file_size"] or 0)
            kind = int(row["kind"] or 0)  # 0=photo, 1=video

            # ZDIRECTORY is one of:
            #   "DCIM/134APPLE"         → legacy DCIM path
            #   "PhotoData/..."         → already an absolute-relative path (e.g. shared albums)
            #   single hex char "2"     → /PhotoData/Originals/<hex>/<file>
            if directory.startswith("DCIM"):
                full_path = f"/{directory}/{filename}"
            elif directory.startswith("PhotoData"):
                # Shared album / cloud data — path is already relative to device root
                full_path = f"/{directory}/{filename}"
            else:
                full_path = f"/PhotoData/Originals/{directory}/{filename}"
            stem = Path(filename).stem
            key = (directory, stem)

            if kind == 1 or ext in {".mov", ".mp4", ".m4v"}:
                media_type = "video"
            else:
                media_type = "photo"

            # Shared album photos live in PhotoCloudSharingData — they appear
            # in the Photos DB but are not accessible via AFC. Exclude entirely
            # so they don't inflate counts or show as failures.
            if "PhotoCloudSharingData" in full_path:
                continue

            is_stub = (media_type == "photo" and 0 < file_size < 51_200)
            is_screenshot = (int(row["kind_subtype"] or 0) == 10)

            asset = PhotoAsset(
                filename=filename,
                source_path=full_path,
                date_taken=date_taken,
                file_size=file_size,
                media_type=media_type,
                live_photo_pair_id=None,  # filled below
                is_icloud_stub=is_stub,
                is_screenshot=is_screenshot,
            )
            stem_map.setdefault(key, {})[media_type] = asset
            assets.append(asset)

        # Assign Live Photo pair IDs
        for (directory, stem), parts in stem_map.items():
            if "photo" in parts and "video" in parts:
                pair_id = f"LP_{stem}"
                parts["photo"].live_photo_pair_id = pair_id
                parts["photo"].media_type = "live_photo_image"
                parts["video"].live_photo_pair_id = pair_id
                parts["video"].media_type = "live_photo_video"

        return assets

    # ------------------------------------------------------------------ #
    # Fallback: partial file read + EXIF extraction                       #
    # ------------------------------------------------------------------ #

    async def _read_partial(self, path: str, max_bytes: int) -> bytes:
        try:
            fh = await self._afc.open(path, "r")
            data = await fh.read(max_bytes)
            await fh.close()
            return bytes(data)
        except Exception:
            pass
        try:
            data = await self._afc.get_file_contents(path)
            return bytes(data[:max_bytes])
        except Exception:
            return b""

    @staticmethod
    def _parse_exif_date(raw: bytes) -> Optional[datetime]:
        try:
            return datetime.strptime(raw.decode(), "%Y:%m:%d %H:%M:%S")
        except Exception:
            return None

    def _date_from_jpeg(self, data: bytes) -> Optional[datetime]:
        try:
            import piexif
            exif = piexif.load(data)
            raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
            if raw:
                return self._parse_exif_date(raw)
            raw = exif.get("0th", {}).get(piexif.ImageIFD.DateTime)
            if raw:
                return self._parse_exif_date(raw)
        except Exception:
            pass
        return None

    def _date_from_heic(self, data: bytes) -> Optional[datetime]:
        try:
            import piexif
            import pillow_heif
            heif = pillow_heif.read_heif(data)
            exif_data = heif.info.get("exif")
            if exif_data:
                exif = piexif.load(exif_data)
                raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
                if raw:
                    return self._parse_exif_date(raw)
        except Exception:
            pass
        return None

    def _date_from_quicktime(self, data: bytes) -> Optional[datetime]:
        QT_EPOCH_OFFSET = 2_082_844_800
        try:
            idx = 0
            while idx + 8 <= len(data):
                box_size = struct.unpack(">I", data[idx:idx + 4])[0]
                box_type = data[idx + 4:idx + 8]
                if box_type == b"mvhd":
                    version = data[idx + 8] if idx + 8 < len(data) else 0
                    if version == 0 and idx + 16 <= len(data):
                        ts = struct.unpack(">I", data[idx + 12:idx + 16])[0]
                    elif version == 1 and idx + 20 <= len(data):
                        ts = struct.unpack(">Q", data[idx + 12:idx + 20])[0]
                    else:
                        break
                    unix_ts = ts - QT_EPOCH_OFFSET
                    if unix_ts > 0:
                        return datetime.fromtimestamp(unix_ts)
                if box_size < 8:
                    break
                idx += box_size
        except Exception:
            pass
        return None

    async def _get_exif_date(self, path: str, ext: str, st_fallback: datetime) -> datetime:
        if ext in (".jpg", ".jpeg"):
            data = await self._read_partial(path, _JPEG_READ)
            result = self._date_from_jpeg(data)
        elif ext == ".heic":
            data = await self._read_partial(path, _HEIC_READ)
            result = self._date_from_heic(data)
        elif ext in (".mov", ".mp4", ".m4v"):
            data = await self._read_partial(path, _VIDEO_READ)
            result = self._date_from_quicktime(data)
        else:
            result = None
        return result if result is not None else st_fallback

    # ------------------------------------------------------------------ #
    # Fallback DCIM scan (slow — reads EXIF from every file)             #
    # ------------------------------------------------------------------ #

    async def _async_scan_dcim(
        self,
        on_progress=None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[PhotoAsset]:
        try:
            all_folders = await self._afc.listdir("/DCIM")
        except Exception as e:
            raise RuntimeError(f"Cannot list /DCIM on device: {e}") from e

        folders = sorted([f for f in all_folders if not f.startswith(".")], reverse=True)

        folder_fnames: Dict[str, List[str]] = {}
        total_files = 0
        for folder in folders:
            fnames: List[str] = []
            try:
                for fname in await self._afc.listdir(f"/DCIM/{folder}"):
                    if Path(fname).suffix.lower() in MEDIA_EXTS:
                        fnames.append(fname)
                        total_files += 1
            except Exception:
                pass
            folder_fnames[folder] = sorted(fnames)

        assets: List[PhotoAsset] = []
        processed = 0

        for folder in folders:
            fnames = folder_fnames.get(folder, [])
            if not fnames:
                continue

            folder_path = f"/DCIM/{folder}"

            stem_map: Dict[str, List[tuple]] = {}
            for fname in fnames:
                stem = Path(fname).stem
                ext = Path(fname).suffix.lower()
                stem_map.setdefault(stem, []).append((fname, ext))

            pair_ids: Dict[str, str] = {}
            for stem, entries in stem_map.items():
                exts = {e for _, e in entries}
                if bool(exts & {".jpg", ".jpeg", ".heic"}) and ".mov" in exts:
                    pair_ids[stem] = f"LP_{stem}"

            image_dates: Dict[str, datetime] = {}

            for stem, entries in stem_map.items():
                for fname, ext in entries:
                    processed += 1
                    if on_progress:
                        on_progress(processed, total_files)

                    full_path = f"{folder_path}/{fname}"
                    pair_id = pair_ids.get(stem)

                    if pair_id and ext in LIVE_PHOTO_VIDEO_EXTS:
                        media_type = "live_photo_video"
                    elif pair_id:
                        media_type = "live_photo_image"
                    elif ext in {".mov", ".mp4", ".m4v"}:
                        media_type = "video"
                    else:
                        media_type = "photo"

                    file_size = 0
                    st_date = datetime.now()
                    try:
                        stat = await self._afc.os_stat(full_path)
                        file_size = int(stat.st_size)
                        ts = stat.st_birthtime or stat.st_mtime
                        st_date = datetime.fromtimestamp(ts)
                    except Exception:
                        pass

                    if media_type == "live_photo_video" and stem in image_dates:
                        date_taken = image_dates[stem]
                    else:
                        date_taken = await self._get_exif_date(full_path, ext, st_date)
                        if media_type in ("photo", "live_photo_image"):
                            image_dates[stem] = date_taken

                    if start_date and date_taken < start_date:
                        continue
                    if end_date and date_taken > end_date:
                        continue

                    is_stub = (
                        media_type in ("photo", "live_photo_image")
                        and 0 < file_size < 51_200
                    )

                    assets.append(PhotoAsset(
                        filename=fname,
                        source_path=full_path,
                        date_taken=date_taken,
                        file_size=file_size,
                        media_type=media_type,
                        live_photo_pair_id=pair_id,
                        is_icloud_stub=is_stub,
                    ))

        if self._info:
            self._info["total_count"] = len(assets)

        return assets
