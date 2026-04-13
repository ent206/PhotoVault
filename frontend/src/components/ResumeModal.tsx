import { motion } from "framer-motion"
import { format } from "date-fns"
import type { IncompleteSession } from "../lib/types"
import { api } from "../lib/api"
import { useAppStore } from "../store/useAppStore"

interface Props {
  session: IncompleteSession
}

export default function ResumeModal({ session }: Props) {
  const setResumeSession = useAppStore((s) => s.setResumeSession)
  const navigate = useAppStore((s) => s.navigate)
  const setDestination = useAppStore((s) => s.setDestination)

  const started = format(new Date(session.started_at), "MMM d, yyyy 'at' h:mm a")
  const pct = Math.round((session.completed_count / session.total_files) * 100)

  async function handleResume() {
    setDestination(session.destination_path)
    useAppStore.getState().setTransferSessionId(session.session_id)
    setResumeSession(null)
    navigate("progress")
  }

  async function handleStartFresh() {
    await api.dismissSession(session.session_id)
    setResumeSession(null)
  }

  return (
    <motion.div
      className="absolute inset-0 z-50 flex items-end justify-center pb-10 px-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
    >
      <div
        className="absolute inset-0 bg-bg/70 backdrop-blur-md"
        onClick={handleStartFresh}
      />

      <motion.div
        className="relative w-full max-w-sm card p-6 shadow-card"
        initial={{ y: 28, opacity: 0 }}
        animate={{ y: 0, opacity: 1, transition: { delay: 0.05, duration: 0.3, ease: "easeOut" } }}
        exit={{ y: 28, opacity: 0, transition: { duration: 0.2 } }}
      >
        {/* Amber accent line */}
        <div className="absolute top-0 left-6 right-6 h-px bg-amber/30 rounded-full" />

        <p className="label-xs mb-3">Incomplete Transfer Found</p>
        <h2 className="font-display text-display-md text-text font-light mb-1">
          Resume where you left off?
        </h2>
        <p className="text-sm text-muted font-sans mb-5">
          {started} · {session.completed_count.toLocaleString()} of {session.total_files.toLocaleString()} files
        </p>

        {/* Progress */}
        <div className="w-full h-px bg-border rounded-full overflow-hidden mb-1">
          <div className="h-px bg-amber transition-all" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-[11px] text-muted font-mono mb-6">{pct}% complete</p>

        <div className="flex gap-2.5">
          <button className="btn-amber flex-1 text-sm" onClick={handleResume}>
            Resume Transfer
          </button>
          <button className="btn-ghost flex-1 text-sm" onClick={handleStartFresh}>
            Start Fresh
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
