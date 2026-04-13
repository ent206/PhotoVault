import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.device.base import DeviceInterface
from src.models import PhotoAsset, FileRecord, TransferSession, TransferStatus
from src.session_log import SessionLog


@dataclass
class TransferOptions:
    safe_mode: bool = True
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TransferProgress:
    current_filename: str = ""
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    speed_mbps: float = 0.0
    eta_seconds: float = 0.0


class TransferEngine:
    SLEEP_RETRY_ATTEMPTS = 5
    SLEEP_RETRY_DELAY = 2  # seconds between retries

    def __init__(
        self,
        device: DeviceInterface,
        destination: Path,
        session_log: SessionLog,
        options: TransferOptions,
        on_progress: Optional[Callable[[TransferProgress], None]] = None,
        on_device_sleeping: Optional[Callable[[int], None]] = None,
        on_device_resumed: Optional[Callable[[], None]] = None,
    ):
        self.device = device
        self.destination = Path(destination)
        self.log = session_log
        self.options = options
        self.on_progress = on_progress
        self.on_device_sleeping = on_device_sleeping
        self.on_device_resumed = on_device_resumed
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._pause.set()  # not paused initially

    def cancel(self) -> None:
        self._cancel.set()

    def pause(self) -> None:
        self._pause.clear()

    def resume_pause(self) -> None:
        self._pause.set()

    def transfer(self, assets: List[PhotoAsset]) -> Dict:
        """Run the full transfer. Returns summary dict."""
        # Refresh the device connection before starting — lockdown may have
        # timed out while the user was on the summary screen.
        if hasattr(self.device, '_reconnect'):
            try:
                self.device._reconnect()
            except Exception:
                pass  # Will fail on first read if truly disconnected

        session = self._build_session(assets)
        self.log.save(session)

        results = {"completed": 0, "failed": 0, "skipped": 0, "failed_files": []}
        start_time = datetime.now()

        progress = TransferProgress(
            files_total=len(session.files),
            bytes_total=session.total_size_bytes,
        )

        for record in session.files:
            # Skip files already completed from a prior session (resume)
            if record.status == TransferStatus.COMPLETED:
                results["skipped"] += 1
                progress.files_done += 1
                continue

            if self._cancel.is_set():
                break
            self._pause.wait()

            progress.current_filename = record.filename
            if self.on_progress:
                self.on_progress(progress)

            dest_path = Path(record.destination_path)

            # Duplicate detection: same name + same size at destination
            if self._is_duplicate(dest_path, record.file_size):
                self.log.update_file(session.session_id, record.filename, TransferStatus.SKIPPED)
                results["skipped"] += 1
                progress.files_done += 1
                continue

            # Atomic transfer
            partial_path = dest_path.with_suffix(dest_path.suffix + ".photovault_partial")
            try:
                self.log.update_file(session.session_id, record.filename, TransferStatus.IN_PROGRESS)
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                data = self._read_with_retry(self._asset_for_record(assets, record))
                actual_size = len(data)
                partial_path.write_bytes(data)

                # Verify
                checksum = None
                if self.options.safe_mode:
                    checksum = hashlib.md5(data).hexdigest()
                    on_disk_checksum = hashlib.md5(partial_path.read_bytes()).hexdigest()
                    if checksum != on_disk_checksum:
                        raise ValueError(f"Checksum mismatch for {record.filename}")
                # No size-mismatch check when file_size is unknown (0 from DB)

                # Atomic rename: only clean final name after verify passes
                partial_path.rename(dest_path)

                self.log.update_file(
                    session.session_id, record.filename,
                    TransferStatus.COMPLETED, checksum=checksum
                )
                results["completed"] += 1
                progress.bytes_done += actual_size

            except Exception as exc:
                # Clean up partial — never leave corrupted files with clean names
                partial_path.unlink(missing_ok=True)
                self.log.update_file(
                    session.session_id, record.filename,
                    TransferStatus.FAILED, error=str(exc)
                )
                results["failed"] += 1
                results["failed_files"].append(record.filename)

            progress.files_done += 1
            elapsed = (datetime.now() - start_time).total_seconds() or 0.001
            progress.speed_mbps = (progress.bytes_done / 1_048_576) / elapsed
            if progress.speed_mbps > 0 and progress.bytes_total > progress.bytes_done:
                remaining = progress.bytes_total - progress.bytes_done
                progress.eta_seconds = (remaining / 1_048_576) / progress.speed_mbps
            if self.on_progress:
                self.on_progress(progress)

        return results

    def _build_session(self, assets: List[PhotoAsset]) -> TransferSession:
        """Build TransferSession. Honors prior completed files for resume."""
        # Try to load existing session for resume
        completed_filenames = set()
        try:
            existing = self.log.load(self.options.session_id)
            completed_filenames = {
                f.filename for f in existing.files
                if f.status == TransferStatus.COMPLETED
            }
        except Exception:
            pass

        files = []
        for asset in assets:
            dest_path = self._dest_path_for(asset)
            status = TransferStatus.COMPLETED if asset.filename in completed_filenames else TransferStatus.PENDING
            files.append(FileRecord(
                filename=asset.filename,
                source_path=asset.source_path,
                destination_path=str(dest_path),
                file_size=asset.file_size,
                status=status,
            ))

        return TransferSession(
            session_id=self.options.session_id,
            started_at=datetime.now(),
            source_device=self.device.device_info()["model"],
            destination_path=str(self.destination),
            total_files=len(files),
            files=files,
        )

    def _dest_path_for(self, asset: PhotoAsset) -> Path:
        """Returns Year/MM - Month/filename path under destination."""
        month_folder = asset.date_taken.strftime("%m - %B")  # e.g. "03 - March"
        year = str(asset.date_taken.year)
        return self.destination / year / month_folder / asset.filename

    def _is_duplicate(self, dest_path: Path, file_size: int) -> bool:
        """A file is a duplicate if it exists at destination with content.
        If file_size is known, verify sizes match. If unknown (0 from DB),
        treat as duplicate if destination file exists and has any content.
        """
        if not dest_path.exists():
            return False
        dest_size = dest_path.stat().st_size
        if file_size == 0:
            return dest_size > 0  # Unknown size — skip if destination has content
        return dest_size == file_size

    def _asset_for_record(self, assets: List[PhotoAsset], record: FileRecord) -> PhotoAsset:
        return next(a for a in assets if a.filename == record.filename)

    def _read_with_retry(self, asset: PhotoAsset) -> bytes:
        """Read file from device, retrying on transient errors.

        The sleep banner is shown only after the SECOND failure — a single
        hiccup is silently retried so brief AFC glitches don't alarm the user.
        """
        import time
        last_exc: Optional[Exception] = None
        for attempt in range(self.SLEEP_RETRY_ATTEMPTS):
            try:
                return self.device.read_file(asset)
            except Exception as exc:
                last_exc = exc
                if self._cancel.is_set():
                    raise
                # First failure: silent retry. Second+: show sleep banner.
                if attempt > 0 and self.on_device_sleeping:
                    self.on_device_sleeping(self.SLEEP_RETRY_DELAY)
                time.sleep(self.SLEEP_RETRY_DELAY)
                if attempt > 0 and self.on_device_resumed:
                    self.on_device_resumed()
        raise last_exc

    @staticmethod
    def cleanup_partials(directory: Path) -> int:
        """Remove any leftover .photovault_partial files. Returns count removed."""
        count = 0
        for p in Path(directory).rglob("*.photovault_partial"):
            p.unlink()
            count += 1
        return count
