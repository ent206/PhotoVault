import { useEffect, useState } from "react"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import type { TransferSummary } from "../lib/types"

export default function SummaryScreen() {
  const navigate           = useAppStore((s) => s.navigate)
  const assets             = useAppStore((s) => s.assets)
  const destination        = useAppStore((s) => s.destination)!
  const safeMode           = useAppStore((s) => s.safeMode)
  const setSafeMode        = useAppStore((s) => s.setSafeMode)
  const setTransferSession = useAppStore((s) => s.setTransferSessionId)
  const clearTransfer      = useAppStore((s) => s.clearTransfer)

  const [summary, setSummary] = useState<TransferSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    const ids = assets.map((a) => a.id)
    api.getTransferSummary(ids, destination).then((res) => {
      setLoading(false)
      if (res.ok) setSummary(res as unknown as TransferSummary)
      else setError(res.error ?? "Failed to compute summary")
    })
  }, [])

  async function handleStart() {
    if (!summary) return
    clearTransfer()
    const ids = assets.map((a) => a.id)
    const res = await api.startTransfer(ids, destination, safeMode)
    if (res.ok && res.session_id) {
      setTransferSession(res.session_id)
      navigate("progress")
    }
  }

  function etaLabel(secs: number) {
    if (secs < 60)   return `~${secs}s`
    if (secs < 3600) return `~${Math.round(secs / 60)}m`
    return `~${Math.floor(secs / 3600)}h ${Math.round((secs % 3600) / 60)}m`
  }

  const destShort = destination.split("/").filter(Boolean).pop() ?? destination

  return (
    <div className="screen overflow-y-auto">
      <div className="max-w-lg mx-auto w-full px-8 py-10">

        <button
          className="flex items-center gap-1.5 text-xs text-muted hover:text-text transition-colors mb-10"
          onClick={() => navigate("dates")}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back
        </button>

        <div className="mb-10">
          <p className="label-xs mb-3">Step 4 of 4</p>
          <h1 className="font-display text-display-lg text-text font-light">
            Ready to<br /><span className="italic text-amber/80">Transfer</span>
          </h1>
          <p className="text-sm text-muted font-sans mt-3">Review the details before starting.</p>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted mb-8">
            <span className="inline-block w-3 h-3 border border-amber/40 border-t-amber rounded-full animate-spin" />
            Calculating…
          </div>
        )}

        {error && <p className="text-danger text-sm mb-8">{error}</p>}

        {summary && (
          <>
            {/* Summary table */}
            <div className="card overflow-hidden mb-6">
              {[
                { label: "Photos",                value: summary.photos.toLocaleString() },
                { label: "Videos",                value: summary.videos.toLocaleString() },
                { label: "Total Size",            value: summary.total_size_human },
                { label: "Destination",           value: destShort },
                { label: "Estimated Time",        value: etaLabel(summary.eta_seconds) },
                { label: "Duplicates (will skip)",value: summary.duplicates.toLocaleString() },
              ].map(({ label, value }, i, arr) => (
                <div
                  key={label}
                  className={`flex items-center justify-between px-5 py-3.5 ${
                    i < arr.length - 1 ? "border-b border-border" : ""
                  }`}
                >
                  <span className="text-sm text-muted font-sans">{label}</span>
                  <span className="text-sm text-text font-sans font-medium">{value}</span>
                </div>
              ))}

              {summary.stubs > 0 && (
                <div className="flex items-center justify-between px-5 py-3.5 border-t border-border bg-warn/[0.05]">
                  <span className="text-sm text-warn font-sans">iCloud Placeholders</span>
                  <span className="text-sm text-warn font-sans">{summary.stubs} — originals not on device</span>
                </div>
              )}
            </div>

            {/* Space warning */}
            {!summary.space_ok && (
              <div className="mb-6 px-4 py-3 rounded-xl border border-danger/20 bg-danger/[0.07]">
                <p className="text-sm text-danger font-sans">
                  ✗ Not enough space — {summary.free_human} available, need {summary.total_size_human}
                </p>
              </div>
            )}

            {/* Safe mode toggle */}
            <button
              onClick={() => setSafeMode(!safeMode)}
              className="w-full card px-5 py-4 flex items-center justify-between mb-8 hover:border-border-hi transition-colors"
            >
              <div className="text-left flex-1 mr-4">
                <p className="text-sm font-medium font-sans text-text">Safe Mode (MD5 Verification)</p>
                <p className="text-xs text-muted font-sans mt-0.5 leading-relaxed">
                  Confirms every file copied correctly, bit for bit. Slightly slower.
                </p>
              </div>
              <div className={`toggle-track shrink-0 ${safeMode ? "bg-amber" : "bg-white/10"}`}>
                <div className={`toggle-thumb ${safeMode ? "left-[22px]" : "left-[3px]"}`} />
              </div>
            </button>

            <button
              className="btn-amber w-full py-3.5 text-sm"
              onClick={handleStart}
              disabled={!summary.space_ok}
            >
              Start Transfer
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </button>
          </>
        )}
      </div>
    </div>
  )
}
