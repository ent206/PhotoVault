import { useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import ProgressBar from "../components/ProgressBar"

export default function CompleteScreen() {
  const navigate      = useAppStore((s) => s.navigate)
  const results       = useAppStore((s) => s.transferResults)
  const assets        = useAppStore((s) => s.assets)
  const destination   = useAppStore((s) => s.destination)!
  const clearTransfer = useAppStore((s) => s.clearTransfer)
  const dp            = useAppStore((s) => s.deleteProgress)
  const dr            = useAppStore((s) => s.deleteResults)

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  if (!results) return null

  const safe       = results.completed + results.skipped
  const hasFailed  = results.failed > 0
  const allFailed  = safe === 0

  const deletableIds = assets
    .filter((a) => !results.failed_files.includes(a.filename))
    .map((a) => a.id)

  async function handleStartDelete() {
    setShowDeleteConfirm(false)
    await api.startDelete(deletableIds, destination)
  }

  function handleTransferMore() {
    clearTransfer()
    navigate("dates")
  }

  const isDeleting = !!dp && !dr
  const deleteDone = !!dr

  const statusColor = allFailed ? "text-danger" : hasFailed ? "text-warn" : "text-success"
  const statusIcon  = allFailed ? "✗" : hasFailed ? "!" : "✓"

  return (
    <div className="screen overflow-y-auto">

      {/* Delete confirmation modal */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-md px-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="card p-7 max-w-sm w-full shadow-card"
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1, transition: { duration: 0.2 } }}
              exit={{ scale: 0.96, opacity: 0 }}
            >
              <div className="h-px bg-danger/25 rounded-full mb-6" />
              <h2 className="font-display text-xl text-text font-light mb-2">
                Permanently Delete Files?
              </h2>
              <p className="text-sm text-muted font-sans mb-7 leading-relaxed">
                {deletableIds.length.toLocaleString()} files will be permanently deleted from your
                iPhone. Your backup will not be affected.
              </p>
              <div className="flex gap-2.5">
                <button className="btn-danger flex-1 text-sm" onClick={handleStartDelete}>
                  Delete {deletableIds.length.toLocaleString()} Files
                </button>
                <button className="btn-ghost flex-1 text-sm" onClick={() => setShowDeleteConfirm(false)}>
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="max-w-lg mx-auto w-full px-8 py-10">

        {/* Header */}
        <motion.div
          className="flex flex-col items-center mb-10 text-center"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.4 } }}
        >
          {/* Status badge */}
          <motion.div
            className={`w-14 h-14 rounded-full border flex items-center justify-center mb-6 ${
              allFailed
                ? "border-danger/30 bg-danger/[0.08]"
                : hasFailed
                ? "border-warn/30 bg-warn/[0.08]"
                : "border-success/30 bg-success/[0.08]"
            }`}
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, transition: { type: "spring", stiffness: 180, delay: 0.1 } }}
          >
            <span className={`font-display text-2xl font-light ${statusColor}`}>{statusIcon}</span>
          </motion.div>

          <p className="label-xs mb-3">Transfer Complete</p>
          <h1 className={`font-display text-display-lg font-light ${statusColor}`}>
            {allFailed ? "All files failed" : hasFailed ? `${results.failed} file${results.failed > 1 ? "s" : ""} failed` : "Success"}
          </h1>
        </motion.div>

        {/* Results table */}
        <div className="card overflow-hidden mb-6">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
            <span className="text-sm text-muted font-sans">Newly transferred</span>
            <span className="text-sm text-text font-sans font-medium">{results.completed.toLocaleString()}</span>
          </div>
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-border">
            <span className="text-sm text-muted font-sans">Already backed up</span>
            <span className="text-sm text-text font-sans font-medium">{results.skipped.toLocaleString()}</span>
          </div>
          <div className="flex items-center justify-between px-5 py-3.5 bg-white/[0.02]">
            <span className="text-sm text-text font-sans font-medium">Total safe copies</span>
            <span className="text-sm text-amber font-sans font-semibold">{safe.toLocaleString()}</span>
          </div>
          {hasFailed && (
            <div className="flex items-center justify-between px-5 py-3.5 border-t border-border bg-danger/[0.04]">
              <span className="text-sm text-danger font-sans">Could not be read</span>
              <span className="text-sm text-danger font-medium font-sans">{results.failed.toLocaleString()}</span>
            </div>
          )}
        </div>

        {/* Failed files list */}
        {hasFailed && results.failed_files.length > 0 && (
          <details className="card mb-5 overflow-hidden">
            <summary className="px-5 py-3 text-xs text-muted font-sans cursor-pointer hover:text-text transition-colors">
              Show {results.failed_files.length} failed file{results.failed_files.length > 1 ? "s" : ""}
            </summary>
            <div className="max-h-28 overflow-y-auto px-5 pb-3 border-t border-border">
              {results.failed_files.map((f) => (
                <p key={f} className="text-xs text-danger font-mono py-0.5">{f}</p>
              ))}
            </div>
          </details>
        )}

        {/* Delete section */}
        {!deleteDone && safe > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { delay: 0.4 } }}
            className="mb-4"
          >
            {isDeleting && dp ? (
              <div className="card p-5 mb-4">
                <p className="text-xs text-muted font-sans mb-3">
                  Deleting {dp.done.toLocaleString()} of {dp.total.toLocaleString()} files…
                </p>
                <ProgressBar pct={dp.pct} glow height="h-[3px]" />
                {dp.freed_bytes > 0 && (
                  <p className="text-xs text-amber font-mono mt-2.5">{dp.freed_human} freed</p>
                )}
              </div>
            ) : (
              <button
                className="btn-ghost w-full py-3 mb-3 text-sm border-border-hi hover:border-amber/30 hover:text-amber hover:bg-amber/[0.04]"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Free Up iPhone Space
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6l-1 14H6L5 6"/>
                  <path d="M10 11v6M14 11v6"/>
                  <path d="M9 6V4h6v2"/>
                </svg>
              </button>
            )}
            {hasFailed && !isDeleting && (
              <p className="text-[11px] text-muted font-sans text-center">
                {results.failed} unreadable file{results.failed > 1 ? "s" : ""} will not be deleted
              </p>
            )}
          </motion.div>
        )}

        {/* Delete result */}
        {deleteDone && dr && (
          <div className="card p-5 mb-4 border-success/20 bg-success/[0.04]">
            <p className="text-sm font-medium font-sans text-success mb-0.5">
              {dr.freed_human} freed on your iPhone
            </p>
            <p className="text-xs text-muted font-sans">
              {dr.deleted.toLocaleString()} deleted
              {dr.failed > 0 && `, ${dr.failed} could not be removed`}
            </p>
          </div>
        )}

        {/* Nav */}
        <div className="flex gap-2.5 mt-2">
          <button className="btn-ghost flex-1 text-sm" onClick={handleTransferMore}>
            Transfer More
          </button>
          <button className="btn-ghost flex-1 text-sm" onClick={() => navigate("connect")}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
