import { useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import ProgressBar from "../components/ProgressBar"

export default function ProgressScreen() {
  const navigate         = useAppStore((s) => s.navigate)
  const transferProgress = useAppStore((s) => s.transferProgress)
  const transferError    = useAppStore((s) => s.transferError)
  const transferPaused   = useAppStore((s) => s.transferPaused)
  const deviceSleeping   = useAppStore((s) => s.deviceSleeping)
  const deviceSleepRetryIn = useAppStore((s) => s.deviceSleepRetryIn)

  const [showCancelConfirm, setShowCancelConfirm] = useState(false)

  const p    = transferProgress
  const pct  = p?.pct ?? 0
  const isDone = p ? p.files_done >= p.files_total && p.files_total > 0 : false

  function etaLabel(secs: number) {
    if (secs <= 0)   return "Almost done"
    if (secs < 60)   return `${secs}s remaining`
    if (secs < 3600) return `${Math.round(secs / 60)}m remaining`
    return `${Math.floor(secs / 3600)}h ${Math.round((secs % 3600) / 60)}m remaining`
  }

  async function handlePauseResume() {
    if (transferPaused) await api.resumeTransfer()
    else await api.pauseTransfer()
  }

  async function handleCancel() {
    await api.cancelTransfer()
    navigate("connect")
  }

  return (
    <div className="screen items-center justify-center relative">
      {/* Cancel confirm */}
      <AnimatePresence>
        {showCancelConfirm && (
          <motion.div
            className="absolute inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="card p-7 max-w-sm w-full mx-6 shadow-card"
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1, transition: { duration: 0.2 } }}
              exit={{ scale: 0.96, opacity: 0 }}
            >
              {/* Amber top line */}
              <div className="h-px bg-amber/25 rounded-full mb-6" />
              <h2 className="font-display text-xl text-text font-light mb-2">Cancel Transfer?</h2>
              <p className="text-sm text-muted font-sans mb-7 leading-relaxed">
                Files transferred so far are kept. You can resume this session later.
              </p>
              <div className="flex gap-2.5">
                <button className="btn-danger flex-1 text-sm" onClick={handleCancel}>Yes, Cancel</button>
                <button className="btn-ghost flex-1 text-sm" onClick={() => setShowCancelConfirm(false)}>Keep Going</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main content */}
      <div className="relative z-10 w-full max-w-md px-8">

        {/* Title */}
        <div className="text-center mb-12">
          <p className="label-xs mb-3">PhotoVault</p>
          <h1 className="font-display text-display-lg text-text font-light">
            {transferPaused ? "Paused" : isDone ? "Finalizing…" : "Transferring"}
          </h1>
        </div>

        {/* Current filename */}
        <div className="h-5 mb-6 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.p
              key={p?.current_filename}
              className="text-xs text-muted font-mono truncate text-center"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.2 } }}
              exit={{ opacity: 0, y: -4, transition: { duration: 0.12 } }}
            >
              {p?.current_filename ?? ""}
            </motion.p>
          </AnimatePresence>
        </div>

        {/* Progress bar */}
        <div className="mb-6">
          <ProgressBar pct={pct} glow height="h-[3px]" />
          <div className="flex justify-between mt-2">
            <span className="text-[11px] text-muted font-mono">
              {p ? `${p.files_done.toLocaleString()} / ${p.files_total.toLocaleString()}` : "—"}
            </span>
            <span className="text-[11px] text-amber font-mono">
              {Math.round(pct * 100)}%
            </span>
          </div>
        </div>

        {/* Stat pills */}
        <div className="flex justify-center gap-2.5 flex-wrap mb-10">
          <StatPill value={p && p.speed_mbps > 0 ? `${p.speed_mbps.toFixed(1)} MB/s` : "—"} label="speed" />
          <StatPill value={p && !isDone ? etaLabel(p.eta_seconds) : isDone ? "Done" : "—"} label="eta" />
        </div>

        {/* Sleep banner */}
        <AnimatePresence>
          {deviceSleeping && (
            <motion.div
              className="mb-8 px-4 py-3 rounded-xl bg-warn/[0.08] border border-warn/20 text-center"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <p className="text-xs text-warn font-sans">
                Connection hiccup — retrying in {deviceSleepRetryIn}s…
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error */}
        {transferError && (
          <div className="mb-8 px-4 py-3 rounded-xl bg-danger/[0.08] border border-danger/20">
            <p className="text-xs text-danger font-sans">{transferError}</p>
          </div>
        )}

        {/* Controls */}
        <div className="flex gap-2.5 justify-center">
          <button
            className="btn-ghost text-sm px-8"
            onClick={handlePauseResume}
            disabled={!!transferError || isDone}
          >
            {transferPaused ? "Resume" : "Pause"}
          </button>
          <button
            className="btn-ghost text-sm px-8 text-danger/70 border-danger/20 hover:text-danger hover:border-danger/40 hover:bg-danger/[0.05]"
            onClick={() => setShowCancelConfirm(true)}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

function StatPill({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/[0.04] border border-border">
      <span className="text-[10px] text-muted font-sans uppercase tracking-wider">{label}</span>
      <span className="text-xs text-text font-mono">{value}</span>
    </div>
  )
}
