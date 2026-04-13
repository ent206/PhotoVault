import { useEffect, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { format, subYears } from "date-fns"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import ProgressBar from "../components/ProgressBar"

const PRESETS = [
  { label: "Last Year",    years: 1 },
  { label: "Last 2 Years", years: 2 },
  { label: "Last 3 Years", years: 3 },
  { label: "All Media",    years: null },
]

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
]

function toIso(y: number, m: number, d: number) {
  return `${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`
}
function daysIn(month: number, year: number) {
  return new Date(year, month, 0).getDate()
}

function DateSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [y, m, d] = value.split("-").map(Number)
  const maxDay = daysIn(m, y)
  const safeD  = Math.min(d, maxDay)
  const years  = Array.from({ length: new Date().getFullYear() - 1999 }, (_, i) => 2000 + i).reverse()

  const sel = "bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text font-sans outline-none focus:border-amber/50 transition-colors cursor-pointer"

  return (
    <div className="flex gap-2">
      <select
        value={m}
        onChange={(e) => onChange(toIso(y, +e.target.value, Math.min(d, daysIn(+e.target.value, y))))}
        className={`${sel} w-36`}
      >
        {MONTHS.map((name, i) => <option key={i+1} value={i+1}>{name}</option>)}
      </select>
      <select
        value={safeD}
        onChange={(e) => onChange(toIso(y, m, +e.target.value))}
        className={`${sel} w-16`}
      >
        {Array.from({ length: maxDay }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
      <select
        value={y}
        onChange={(e) => onChange(toIso(+e.target.value, m, Math.min(d, daysIn(m, +e.target.value))))}
        className={`${sel} w-24`}
      >
        {years.map((yr) => <option key={yr} value={yr}>{yr}</option>)}
      </select>
    </div>
  )
}

export default function DatesScreen() {
  const navigate       = useAppStore((s) => s.navigate)
  const savedRange     = useAppStore((s) => s.dateRange)
  const scanState      = useAppStore((s) => s.scanState)
  const scanProgress   = useAppStore((s) => s.scanProgress)
  const assetStats     = useAppStore((s) => s.assetStats)
  const scanError      = useAppStore((s) => s.scanError)
  const setDateRange   = useAppStore((s) => s.setDateRange)
  const destination    = useAppStore((s) => s.destination)!

  const today = format(new Date(), "yyyy-MM-dd")
  const [startIso, setStartIso] = useState(savedRange?.start ?? format(subYears(new Date(), 1), "yyyy-MM-dd"))
  const [endIso,   setEndIso]   = useState(savedRange?.end   ?? today)
  // null = no preset chosen; undefined = user manually edited dates
  const [activePreset, setActivePreset] = useState<number | null | undefined>(
    savedRange ? undefined : null  // only pre-select nothing; restore preset state is unknown
  )
  // Whether the user has made any deliberate date selection (preset click or manual change)
  const [rangeConfirmed, setRangeConfirmed] = useState(!!savedRange)
  const [spaceWarn, setSpaceWarn]       = useState<{ type: "error" | "warn"; msg: string } | null>(null)
  const [startError, setStartError]     = useState<string | null>(null)
  const [isStarting, setIsStarting]     = useState(false)

  // Clear the optimistic loading state once the store reflects the new scan state
  useEffect(() => {
    if (scanState !== "idle") setIsStarting(false)
  }, [scanState])

  useEffect(() => {
    if (!assetStats || !destination) return
    api.checkSpace(destination, assetStats.total_bytes).then((res) => {
      if (!res.ok) return
      if (!(res as any).ok) {
        setSpaceWarn({ type: "error", msg: `Not enough space — need ${assetStats.total_size_human}` })
      } else if (((res as any).headroom_pct ?? 1) < 0.1) {
        setSpaceWarn({ type: "warn", msg: `Low space after transfer — check destination` })
      } else {
        setSpaceWarn(null)
      }
    })
  }, [assetStats, destination])

  const isAllMedia = activePreset === null && rangeConfirmed

  function applyPreset(years: number | null) {
    const end   = today
    // "All Media" uses 1970-01-01 — predates all iPhones, captures everything
    const start = years === null ? "1970-01-01" : format(subYears(new Date(), years), "yyyy-MM-dd")
    setStartIso(start); setEndIso(end); setActivePreset(years); setRangeConfirmed(true)
  }

  async function handlePreview() {
    setStartError(null)
    setIsStarting(true)
    setDateRange(startIso, endIso)
    const res = await api.startScan(startIso, endIso)
    if (!(res as any).ok) {
      setIsStarting(false)
      setStartError((res as any).error ?? "Failed to start scan")
    }
  }

  const scanning  = scanState === "scanning" || isStarting
  const done      = scanState === "done"
  const hasAssets = done && (assetStats?.count ?? 0) > 0
  const canScan   = rangeConfirmed && !scanning

  let progressLabel = ""
  if (scanProgress) {
    if (scanProgress.phase === "db") {
      const eta = scanProgress.eta_seconds
      const etaStr = eta == null ? "" : eta < 60 ? ` · ${eta}s left` : ` · ${Math.floor(eta/60)}m ${eta%60}s left`
      progressLabel = `Downloading database · ${scanProgress.read_mb?.toFixed(0) ?? 0} / ${scanProgress.total_mb?.toFixed(0) ?? "?"} MB${etaStr}`
    } else {
      progressLabel = `Scanning ${(scanProgress.current ?? 0).toLocaleString()} / ${(scanProgress.total ?? 0).toLocaleString()} files`
    }
  }

  return (
    <div className="screen overflow-y-auto">
      <div className="max-w-lg mx-auto w-full px-8 py-10">

        <button
          className="flex items-center gap-1.5 text-xs text-muted hover:text-text transition-colors mb-10"
          onClick={() => navigate("destination")}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back
        </button>

        <div className="mb-10">
          <p className="label-xs mb-3">Step 3 of 4</p>
          <h1 className="font-display text-display-lg text-text font-light">
            Select<br /><span className="italic text-amber/80">Date Range</span>
          </h1>
          <p className="text-sm text-muted font-sans mt-3">Choose which photos and videos to transfer.</p>
        </div>

        {/* Preset chips */}
        <div className="flex gap-2 flex-wrap mb-8">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p.years)}
              className={`px-4 py-1.5 rounded-full text-xs font-sans transition-all duration-150 border ${
                activePreset !== null && activePreset !== undefined && activePreset === p.years
                  ? "bg-amber text-[#0c0b09] border-amber font-medium"
                  : "border-border text-muted hover:text-text hover:border-border-hi"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Date pickers — hidden when "All Media" is selected */}
        {isAllMedia ? (
          <div className="card p-5 mb-8 flex items-center gap-3">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-amber shrink-0">
              <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
            <p className="text-sm text-muted font-sans">Every photo and video in your library</p>
          </div>
        ) : (
          <div className="card p-5 mb-8">
            <div className="flex flex-col gap-5">
              <div className="flex items-center gap-5">
                <span className="label-xs w-8 shrink-0 text-right">From</span>
                <DateSelect value={startIso} onChange={(v) => { setStartIso(v); setActivePreset(undefined); setRangeConfirmed(true) }} />
              </div>
              <div className="divider" />
              <div className="flex items-center gap-5">
                <span className="label-xs w-8 shrink-0 text-right">To</span>
                <DateSelect value={endIso} onChange={(v) => { setEndIso(v); setActivePreset(undefined); setRangeConfirmed(true) }} />
              </div>
            </div>
          </div>
        )}

        {/* Preview button */}
        <button
          className={`w-full py-3 text-sm rounded-xl border transition-all duration-150 mb-5 font-sans font-medium ${
            !canScan
              ? "border-border text-muted/50 cursor-not-allowed bg-transparent"
              : "btn-amber"
          }`}
          onClick={handlePreview}
          disabled={!canScan}
        >
          {scanning ? "Scanning…" : "Preview Files"}
        </button>

        {/* Scan progress */}
        <AnimatePresence>
          {scanning && scanProgress && (
            <motion.div
              className="mb-5"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <ProgressBar pct={scanProgress.pct} glow height="h-[3px]" />
              <p className="text-xs text-muted font-mono mt-2.5">{progressLabel}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Scan error */}
        {(scanState === "error" || startError) && (
          <p className="text-danger text-sm font-sans mb-5">{startError ?? scanError}</p>
        )}

        {/* Results */}
        <AnimatePresence>
          {done && assetStats && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.3 } }}
              className="mb-8"
            >
              {assetStats.count === 0 ? (
                <div className="card p-4">
                  <p className="text-sm text-muted font-sans">No photos or videos found in that range.</p>
                </div>
              ) : (
                <div className="card p-5">
                  {/* Big count */}
                  <div className="mb-4">
                    <p className="font-display text-3xl text-text font-light">
                      {assetStats.count.toLocaleString()}
                      <span className="text-lg text-muted ml-2 font-sans font-normal">files</span>
                    </p>
                    <p className="text-sm text-amber font-sans mt-1">{assetStats.total_size_human}</p>
                  </div>

                  {/* Breakdown */}
                  <div className="divider mb-4" />
                  <div className="flex gap-6 text-xs text-muted font-sans">
                    <span>{assetStats.photos.toLocaleString()} photos</span>
                    <span>{assetStats.videos.toLocaleString()} videos</span>
                    {assetStats.screenshots > 0 && (
                      <span>{assetStats.screenshots.toLocaleString()} screenshots</span>
                    )}
                  </div>

                  {/* Warnings */}
                  {assetStats.stubs > 0 && (
                    <div className="mt-4 px-3 py-2.5 rounded-lg bg-warn/[0.08] border border-warn/20">
                      <p className="text-xs text-warn font-sans leading-relaxed">
                        ⚠ {assetStats.stubs} file{assetStats.stubs > 1 ? "s are" : " is"} iCloud placeholder{assetStats.stubs > 1 ? "s" : ""}.
                        {" "}Enable "Download and Keep Originals" in iPhone Settings → Photos.
                      </p>
                    </div>
                  )}

                  {spaceWarn && (
                    <div className={`mt-3 px-3 py-2.5 rounded-lg border text-xs font-sans leading-relaxed ${
                      spaceWarn.type === "error"
                        ? "bg-danger/[0.08] border-danger/20 text-danger"
                        : "bg-warn/[0.08] border-warn/20 text-warn"
                    }`}>
                      ⚠ {spaceWarn.msg}
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <button
          className="btn-amber w-full py-3 text-sm"
          onClick={() => navigate("summary")}
          disabled={!hasAssets}
        >
          Continue
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
    </div>
  )
}
