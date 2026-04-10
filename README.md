# PhotoVault

Transfer photos and videos from iPhone to Mac with checksum verification, resume capability, and a clean 7-screen GUI.

## Requirements

- macOS 12+ (Monterey or later)
- Python 3.11+
- iPhone running iOS 15+ (iOS 17+ requires additional tunnel step — see below)

## First-Time Setup

### 1. Install Python 3.11+

**Recommended:** Install from [python.org](https://www.python.org/downloads/) (includes Tk/Tcl for GUI support).

Alternatively via Homebrew with Tk support:
```bash
brew install python@3.12 python-tk@3.12
```

### 2. Clone or download PhotoVault

### 3. Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Generate mock library (for testing without an iPhone)

```bash
python create_mock_library.py
```

This creates `./mock_library/` with ~485 test photos and videos.

## Running

### Mock mode (no iPhone needed — for testing)

```bash
source .venv/bin/activate
python main.py --mock ./mock_library
```

### Real iPhone mode

Connect your iPhone via USB, unlock it, and tap "Trust" when prompted on the iPhone.

```bash
source .venv/bin/activate
python main.py
```

## iOS 17+ Tunnel Requirement

iPhones running iOS 17 or later require a background tunnel service for USB communication via pymobiledevice3.

PhotoVault will detect this automatically and prompt you for your Mac password to start the tunnel service.

**To start it manually before launching PhotoVault:**
```bash
sudo python3 -m pymobiledevice3 remote start-quic-tunnel
```
Keep this terminal running, then launch PhotoVault in another terminal.

## App Flow

1. **Connect** — Plug in iPhone, app detects it automatically
2. **Choose Destination** — Select external drive or folder
3. **Select Dates** — Pick date range (with live count preview)
4. **Review Summary** — Confirm counts, ETA, and enable/disable Safe Mode (MD5 verification)
5. **Transfer** — Live progress with pause/cancel support
6. **Complete** — See results; green button unlocks space-freeing only if 100% verified
7. **Delete** — Two-step confirmation before deleting from iPhone

## Safe Mode

Safe Mode (enabled by default) verifies every file using MD5 checksum after copying. This confirms each file was copied bit-for-bit correctly. It is slightly slower but guarantees data integrity.

Turn it off on the Summary screen to use fast file-size-only verification.

## Resume After Crash

If the app is killed mid-transfer, it will detect the incomplete session on next launch and offer to resume. Already-transferred files are skipped.

## Session Logs

Every transfer creates a JSON log at `./session_logs/<session-id>.json` containing:
- Every file transferred (source path, destination path, file size, checksum)
- Transfer status per file
- Timestamps

## Building a .app (Optional)

```bash
source .venv/bin/activate
pyinstaller photovault.spec
```

Output is in `dist/PhotoVault/`. To create a proper `.app` bundle for distribution, code signing and packaging are required (not covered here).

## Troubleshooting

**"No module named '_tkinter'"**
Your Python was built without Tk support. Install from python.org or run `brew install python-tk@3.12`.

**iPhone not detected**
- Make sure the iPhone is unlocked
- Tap "Trust This Computer" on the iPhone if prompted
- Try a different USB cable or port
- Check that `pymobiledevice3` is installed: `python -m pymobiledevice3 list-devices`

**iOS 17+ connection fails**
Run the tunnel manually: `sudo python3 -m pymobiledevice3 remote start-quic-tunnel`

**iCloud placeholder warning**
Some photos show as low-resolution previews (iCloud stubs). On your iPhone, go to Settings → Photos → Enable "Download and Keep Originals" to download full-resolution versions before transferring.
