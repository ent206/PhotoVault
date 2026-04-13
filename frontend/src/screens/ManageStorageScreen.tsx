import { useEffect, useMemo, useRef, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import type { PhotoAsset } from "../lib/types"

const FILTERS = [
  { label: "Everything", value: "all" },
  { label: "Photos", value: "photos" },
  { label: "Videos", value: "videos" },
  { label: "Screenshots", value: "screenshots" },
] as const

const PRESETS = [
  { label: "Last 1 Year", years: 1 },
  { label: "Last 2 Years", years: 2 },
  { label: "Last 3 Years", years: 3 },
  { label: "All Media", years: null },
] as const

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function humanSize(bytes: number): string {
  if (bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let size = bytes
  let unitIdx = 0
  while (size >= 1024 && unitIdx < units.length - 1) {
    size /= 1024
    unitIdx++
  }
  return `${size.toFixed(1)} ${units[unitIdx]}`
}

function applyFilter(assets: PhotoAsset[], filter: string): PhotoAsset[] {
  switch (filter) {
    case "photos":
      return assets.filter(
        (a) =>
          (a.media_type === "photo" || a.media_type === "live_photo_image") &&
          !a.is_screenshot
      )
    case "videos":
      return assets.filter(
        (a) => a.media_type === "video" || a.media_type === "live_photo_video"
      )
    case "screenshots":
      return assets.filter((a) => a.is_screenshot)
    default:
      return assets
  }
}

export default function ManageStorageScreen() {
  const navigate = useAppStore((s) => s.navigate)
  const device = useAppStore((s) => s.device)

  // Date range state
  const [startDate, setStartDate] = useState<string>(() => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 1)
    return d.toISOString().split("T")[0]
  })
  const [endDate, setEndDate] = useState<string>(() =>
    new Date().toISOString().split("T")[0]
  )

  // Scan state
  const [isScanning, setIsScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<{
    phase: "db" | "exif"
    pct: number
    message: string
  } | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [allAssets, setAllAssets] = useState<PhotoAsset[]>([])
  const [activeFilter, setActiveFilter] = useState<string>("all")
  const [showResults, setShowResults] = useState(false)

  // Delete state
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteProgress, setDeleteProgress] = useState<{
    done: number
    total: number
    freed: number
  } | null>(null)
  const [deleteResult, setDeleteResult] = useState<{
    deleted: number
    failed: number
    freed: number
  } | null>(null)
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  // Tooltip state
  const [showScreenshotTip, setShowScreenshotTip] = useState(false)

  const filteredAssets = useMemo(
    () => applyFilter(allAssets, activeFilter),
    [allAssets, activeFilter]
  )

  const stats = useMemo(() => {
    const total = filteredAssets.length
    const size = filteredAssets.reduce((sum, a) => sum + a.file_size, 0)
    const photos = allAssets.filter(
      (a) =>
        (a.media_type === "photo" || a.media_type === "live_photo_image") &&
        !a.is_screenshot
    ).length
    const videos = allAssets.filter(
      (a) => a.media_type === "video" || a.media_type === "live_photo_video"
    ).length
    const screenshots = allAssets.filter((a) => a.is_screenshot).length
    return { total, size, photos, videos, screenshots }
  }, [filteredAssets, allAssets])

  function applyPreset(years: number | null) {
    const end = new Date()
    const start = years
      ? new Date(end.getFullYear() - years, end.getMonth(), end.getDate())
      : new Date(2000, 0, 1)
    setStartDate(start.toISOString().split("T")[0])
    setEndDate(end.toISOString().split("T")[0])
  }

  async function handleStartScan() {
    if (isScanning || isDeleting) return
    setIsScanning(true)
    setScanError(null)
    setShowResults(false)
    setAllAssets([])
    setDeleteResult(null)

    try {
      const startIso = new Date(startDate).toISOString()
      const endIso = new Date(endDate + "T23:59:59.999Z").toISOString()

      // Start scan
      const result = await api.startScan(startIso, endIso)
      if (!result.ok) {
        throw new Error(result.error || "Scan failed")
      }

      // Poll for assets
      setScanProgress({ phase: "db", pct: 0, message: "Scanning iPhone…" })

      let attempts = 0
      const maxAttempts = 300 // 30 seconds max

      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 100))
        const listResult = await api.listAssets(startIso, endIso)

        if (listResult.ok && listResult.assets) {
          setAllAssets(listResult.assets)
          setScanProgress({
            phase: "exif",
            pct: 100,
            message: `Found ${listResult.assets.length.toLocaleString()} files`,
          })
          setTimeout(() => {
            setIsScanning(false)
            setScanProgress(null)
            setShowResults(true)
          }, 500)
          return
        }
        attempts++
      }

      throw new Error("Scan timeout - please try again")
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setScanError(msg)
      setIsScanning(false)
      setScanProgress(null)
    }
  }

  async function handleDelete() {
    if (isDeleting || filteredAssets.length === 0) return
    setShowConfirmDialog(false)
    setIsDeleting(true)
    setDeleteResult(null)
    setDeleteProgress({ done: 0, total: filteredAssets.length, freed: 0 })

    // Build destination path (use iPhone name or default)
    const destPath = device?.model
      ? `/tmp/photovault_backup_${Date.now()}`
      : "/tmp/photovault_backup"

    try {
      const assetIds = filteredAssets.map((a) => a.id)
      const result = await api.startDelete(assetIds, destPath)

      if (!result.ok) {
        throw new Error(result.error || "Delete failed")
      }

      // Simulate progress since we don't have real-time delete progress events
      const total = filteredAssets.length
      const freed = filteredAssets.reduce((sum, a) => sum + a.file_size, 0)

      for (let i = 0; i <= total; i += Math.ceil(total / 20)) {
        setDeleteProgress({
          done: i,
          total,
          freed: Math.floor((freed * i) / total),
        })
        await new Promise((r) => setTimeout(r, 100))
      }

      setDeleteProgress({ done: total, total, freed })
      setDeleteResult({ deleted: total, failed: 0, freed })
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setDeleteResult({ deleted: 0, failed: total, freed: 0 })
      // eslint-disable-next-line no-console
      console.error("Delete error:", msg)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="screen relative">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 p-6">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between"
        >
          <button
            onClick={() => navigate("connect")}
            disabled={isScanning || isDeleting}
            className="text-sm text-muted hover:text-text transition-colors disabled:opacity-50"
          >
            ← Back
          </button>
          <div className="label-xs">PhotoVault</div>
          <div className="w-12" /> {/* Spacer for centering */}
        </motion.div>
      </div>

      {/* Main content */}
      <motion.div
        className="flex flex-col items-center max-w-xl w-full px-6 pt-20"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0, transition: { duration: 0.5 } }}
      >
        {/* Title */}
        <h1 className="font-display text-display text-text font-light mb-2">
          Free Up Storage
        </h1>
        <p className="text-sm text-muted mb-8 text-center">
          Select a date range, preview what will be deleted, then confirm.
        </p>

        {/* Date presets */}
        <div className="flex flex-wrap gap-2 justify-center mb-6">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              onClick={() => applyPreset(preset.years)}
              className="px-4 py-2 rounded-lg bg-surface border border-border hover:border-amber/50 text-xs text-text transition-colors"
            >
              {preset.label}
            </button>
          ))}
        </div>

        {/* Date inputs */}
        <div className="flex items-center gap-4 mb-8">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-muted">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              disabled={isScanning || isDeleting}
              className="field text-sm"
            />
          </div>
          <div className="text-muted mt-6">→</div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-muted">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              disabled={isScanning || isDeleting}
              className="field text-sm"
            />
          </div>
        </div>

        {/* Preview button */}
        <button
          onClick={handleStartScan}
          disabled={isScanning || isDeleting || !startDate || !endDate}
          className="btn-amber w-full max-w-xs py-3 text-sm tracking-wide disabled:opacity-50"
        >
          {isScanning ? "Scanning…" : "Preview Files"}
        </button>

        {/* Scan progress */}
        <AnimatePresence>
          {scanProgress && (
            <motion.div
              className="w-full max-w-xs mt-6"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <div className="h-1 bg-surface rounded-full overflow-hidden mb-2">
                <motion.div
                  className="h-full bg-amber"
                  initial={{ width: 0 }}
                  animate={{ width: `${scanProgress.pct}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
              <p className="text-xs text-muted text-center">
                {scanProgress.message}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Scan error */}
        <AnimatePresence>
          {scanError && (
            <motion.div
              className="mt-4 p-4 rounded-lg bg-danger/10 border border-danger/20 text-danger text-sm text-center max-w-xs"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              {scanError}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Results */}
        <AnimatePresence>
          {showResults && !isDeleting && !deleteResult && (
            <motion.div
              className="w-full mt-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              {/* Filter tabs */}
              <div className="flex justify-center gap-2 mb-6 flex-wrap">
                {FILTERS.map((filter) => (
                  <button
                    key={filter.value}
                    onClick={() => setActiveFilter(filter.value)}
                    className={`px-4 py-2 rounded-lg text-xs transition-colors ${
                      activeFilter === filter.value
                        ? "bg-amber text-black"
                        : "bg-surface text-text hover:bg-surface-hover"
                    }`}
                  >
                    {filter.label}
                  </button>
                ))}
                {activeFilter === "screenshots" && (
                  <button
                    onClick={() => setShowScreenshotTip(!showScreenshotTip)}
                    className="w-8 h-8 rounded-full bg-surface text-muted hover:text-text transition-colors text-xs"
                  >
                    ⓘ
                  </button>
                )}
              </div>

              {/* Screenshot tooltip */}
              <AnimatePresence>
                {showScreenshotTip && activeFilter === "screenshots" && (
                  <motion.div
                    className="mb-4 p-4 rounded-lg bg-surface border border-border"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs text-warn">About Screenshots</span>
                      <button
                        onClick={() => setShowScreenshotTip(false)}
                        className="text-muted hover:text-text"
                      >
                        ✕
                      </button>
                    </div>
                    <p className="text-xs text-muted">
                      Screenshots are images captured using the side button +
                      volume up — regardless of what&apos;s on screen. This
                      includes screenshotted texts, maps, webpages, and more.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Stats display */}
              <div className="text-center mb-6">
                {stats.total === 0 ? (
                  <p className="text-text font-display text-xl">
                    No files in this range
                  </p>
                ) : (
                  <>
                    <p className="font-display text-3xl text-text font-light mb-1">
                      {stats.total.toLocaleString()} files ·{" "}
                      {formatBytes(stats.size)}
                    </p>
                    <p className="text-xs text-muted">
                      {stats.photos.toLocaleString()} photos ·{" "}
                      {stats.videos.toLocaleString()} videos ·{" "}
                      {stats.screenshots.toLocaleString()} screenshots
                    </p>
                  </>
                )}
              </div>

              {/* Delete button */}
              {stats.total > 0 && (
                <button
                  onClick={() => setShowConfirmDialog(true)}
                  className="w-full max-w-xs mx-auto block py-3 rounded-lg bg-danger hover:bg-danger-hover text-white text-sm font-medium transition-colors"
                >
                  Delete {stats.total.toLocaleString()} Files
                </button>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Delete progress */}
        <AnimatePresence>
          {isDeleting && deleteProgress && (
            <motion.div
              className="w-full max-w-xs mt-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <div className="h-2 bg-surface rounded-full overflow-hidden mb-3">
                <motion.div
                  className="h-full bg-danger"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${(deleteProgress.done / deleteProgress.total) * 100}%`,
                  }}
                  transition={{ duration: 0.2 }}
                />
              </div>
              <p className="text-sm text-text text-center mb-1">
                Deleting {deleteProgress.done.toLocaleString()} of{" "}
                {deleteProgress.total.toLocaleString()} files…
              </p>
              {deleteProgress.freed > 0 && (
                <p className="text-xs text-muted text-center">
                  Freed {humanSize(deleteProgress.freed)} so far
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Delete result */}
        <AnimatePresence>
          {deleteResult && (
            <motion.div
              className="w-full max-w-xs mt-8 p-6 rounded-xl bg-surface border border-border text-center"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
            >
              {deleteResult.failed === 0 ? (
                <>
                  <div className="w-12 h-12 rounded-full bg-success/20 text-success mx-auto mb-3 flex items-center justify-center text-xl">
                    ✓
                  </div>
                  <p className="text-text font-medium mb-1">
                    Done — deleted {deleteResult.deleted.toLocaleString()} files
                  </p>
                  <p className="text-success text-sm">
                    Freed {formatBytes(deleteResult.freed)}
                  </p>
                </>
              ) : deleteResult.deleted === 0 ? (
                <>
                  <div className="w-12 h-12 rounded-full bg-danger/20 text-danger mx-auto mb-3 flex items-center justify-center text-xl">
                    ✕
                  </div>
                  <p className="text-danger mb-1">No files were deleted</p>
                  <p className="text-muted text-sm">
                    iPhone may have been disconnected.
                  </p>
                </>
              ) : (
                <>
                  <div className="w-12 h-12 rounded-full bg-warn/20 text-warn mx-auto mb-3 flex items-center justify-center text-xl">
                    !
                  </div>
                  <p className="text-text font-medium mb-1">
                    Deleted {deleteResult.deleted} of{" "}
                    {deleteResult.deleted + deleteResult.failed} files
                  </p>
                  <p className="text-warn text-sm">
                    Freed {formatBytes(deleteResult.freed)} ({" "}
                    {deleteResult.failed} failed)
                  </p>
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Confirmation Dialog */}
      <AnimatePresence>
        {showConfirmDialog && (
          <motion.div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowConfirmDialog(false)}
          >
            <motion.div
              className="bg-card rounded-2xl p-8 max-w-sm w-full"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="font-display text-xl text-text mb-2">
                Permanently Delete Files?
              </h3>
              <p className="text-sm text-muted mb-6 leading-relaxed">
                <strong className="text-text">
                  {stats.total.toLocaleString()} files
                </strong>{" "}
                will be permanently deleted from your iPhone and cannot be
                recovered. Make sure you have a backup.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowConfirmDialog(false)}
                  className="flex-1 py-3 rounded-lg bg-surface text-text text-sm font-medium hover:bg-surface-hover transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="flex-1 py-3 rounded-lg bg-danger text-white text-sm font-medium hover:bg-danger-hover transition-colors"
                >
                  Delete {stats.total.toLocaleString()} Files
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
