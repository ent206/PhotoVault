import { useEffect, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "../store/useAppStore"
import { api } from "../lib/api"
import type { DriveInfo } from "../lib/types"

export default function DestinationScreen() {
  const navigate     = useAppStore((s) => s.navigate)
  const setDest      = useAppStore((s) => s.setDestination)

  const [drives,   setDrives]   = useState<DriveInfo[]>([])
  const [recents,  setRecents]  = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [hoveredRecent, setHoveredRecent] = useState<string | null>(null)
  const [subfolder, setSubfolder] = useState("")
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  useEffect(() => {
    api.listDrives().then((res) => {
      setLoading(false)
      if (res.ok) {
        setDrives(res.drives ?? [])
        setRecents(res.recent_destinations ?? [])
      } else {
        setError(res.error ?? "Failed to load drives")
      }
    })
  }, [])

  async function handleContinue() {
    if (!selected) return
    const res = await api.setDestination(selected, subfolder)
    if (res.ok && res.resolved_path) {
      setDest(res.resolved_path)
      navigate("dates")
    }
  }

  async function handleBrowse() {
    const res = await api.browseFolder()
    if (res.ok && res.path) setSelected(res.path)
  }

  const lastName = (p: string) => p.split("/").filter(Boolean).pop() ?? p
  const resolvedPath = subfolder.trim() ? `${selected}/${subfolder.trim()}` : selected

  return (
    <div className="screen overflow-y-auto">
      <div className="max-w-lg mx-auto w-full px-8 py-10">

        {/* Back */}
        <button
          className="flex items-center gap-1.5 text-xs text-muted hover:text-text transition-colors mb-10"
          onClick={() => navigate("connect")}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back
        </button>

        {/* Header */}
        <div className="mb-10">
          <p className="label-xs mb-3">Step 2 of 4</p>
          <h1 className="font-display text-display-lg text-text font-light">
            Choose<br /><span className="italic text-amber/80">Destination</span>
          </h1>
          <p className="text-sm text-muted font-sans mt-3">Where should your photos be saved?</p>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted mb-8">
            <span className="inline-block w-3 h-3 border border-amber/40 border-t-amber rounded-full animate-spin" />
            Loading drives…
          </div>
        )}
        {error && <p className="text-danger text-sm mb-6">{error}</p>}

        {/* Recents */}
        {recents.length > 0 && (
          <Section label="Recents">
            {recents.map((p) => (
              <DestRow
                key={p}
                icon="🕐"
                label={lastName(p)}
                sub={p}
                selected={selected === p}
                onSelect={() => setSelected(p)}
                onHover={(hovering) => setHoveredRecent(hovering ? p : null)}
                showRemove={hoveredRecent === p}
                onRemove={() => setRecents((prev) => prev.filter((r) => r !== p))}
              />
            ))}
          </Section>
        )}

        {/* Drives */}
        {drives.length > 0 && (
          <Section label="Connected Drives">
            {drives.map((d) => (
              <DestRow
                key={d.path}
                icon={d.is_external ? "💿" : "💻"}
                label={d.name}
                sub={`${d.free_human} free of ${d.total_human}`}
                badge={d.is_external ? "External" : "Internal"}
                selected={selected === d.path}
                onSelect={() => setSelected(d.path)}
              />
            ))}
          </Section>
        )}

        {/* Custom folder */}
        <Section label="Custom Location">
          <button
            onClick={handleBrowse}
            className={`w-full text-left flex items-center gap-3 px-4 py-3.5 rounded-xl border transition-all duration-150 ${
              selected && !drives.find((d) => d.path === selected) && !recents.includes(selected)
                ? "border-amber/40 bg-amber/[0.06]"
                : "border-border hover:border-border-hi hover:bg-white/[0.02]"
            }`}
          >
            <span className="text-muted">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
            </span>
            <span className="text-sm font-sans text-muted-hi">
              {selected && !drives.find((d) => d.path === selected) && !recents.includes(selected)
                ? lastName(selected)
                : "Browse…"}
            </span>
          </button>
        </Section>

        {/* Subfolder */}
        <div className="mb-8">
          <p className="label-xs mb-2">New Subfolder <span className="normal-case text-muted-hi">(optional)</span></p>
          <input
            type="text"
            placeholder="e.g. iPhone Backup 2025"
            value={subfolder}
            onChange={(e) => setSubfolder(e.target.value)}
            className="field text-sm"
          />
        </div>

        {/* Selected path */}
        <AnimatePresence>
          {selected && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mb-6 px-4 py-3 rounded-xl border border-amber/20 bg-amber/[0.05]"
            >
              <p className="label-xs text-amber/70 mb-1">Destination</p>
              <p className="text-xs font-mono text-amber/90 truncate">{resolvedPath}</p>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          className="btn-amber w-full py-3 text-sm"
          onClick={handleContinue}
          disabled={!selected}
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

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-7">
      <p className="label-xs mb-3">{label}</p>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}

function DestRow({
  icon, label, sub, badge, selected, onSelect, onHover, showRemove, onRemove,
}: {
  icon: string; label: string; sub: string; badge?: string; selected: boolean; onSelect: () => void
  onHover?: (hovering: boolean) => void
  showRemove?: boolean
  onRemove?: () => void
}) {
  return (
    <div
      className={`w-full flex items-center gap-2 rounded-xl border transition-all duration-150 ${
        selected
          ? "border-amber/40 bg-amber/[0.07]"
          : "border-border hover:border-border-hi hover:bg-white/[0.02]"
      }`}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
    >
      <button
        onClick={onSelect}
        className="flex-1 text-left flex items-center gap-3.5 px-4 py-3.5"
      >
        <span className="text-base shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium font-sans text-text truncate">{label}</p>
          <p className="text-xs text-muted font-sans truncate mt-0.5">{sub}</p>
        </div>
        {badge && (
          <span className="text-[10px] px-2 py-0.5 rounded-full border border-border text-muted font-sans shrink-0">
            {badge}
          </span>
        )}
        {selected && (
          <span className="text-amber shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </span>
        )}
      </button>
      {showRemove && onRemove && !selected && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="mr-3 px-2 py-1 text-[10px] text-muted hover:text-danger transition-colors"
        >
          Remove
        </button>
      )}
    </div>
  )
}
