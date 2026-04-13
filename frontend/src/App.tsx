import { useEffect } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "./store/useAppStore"
import { waitForApi, api } from "./lib/api"

import ConnectScreen from "./screens/ConnectScreen"
import DestinationScreen from "./screens/DestinationScreen"
import DatesScreen from "./screens/DatesScreen"
import SummaryScreen from "./screens/SummaryScreen"
import ProgressScreen from "./screens/ProgressScreen"
import CompleteScreen from "./screens/CompleteScreen"
import ThemeToggle from "./components/ThemeToggle"

const SLIDE = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" as const } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.15, ease: "easeIn" as const } },
}

export default function App() {
  const screen = useAppStore((s) => s.screen)
  const handleEvent = useAppStore((s) => s.handleEvent)
  const setResumeSession = useAppStore((s) => s.setResumeSession)
  const setTheme = useAppStore((s) => s.setTheme)

  // Register the global Python → React event handler
  useEffect(() => {
    window.__pv = ({ event, data }) => handleEvent(event, data as Record<string, unknown>)
  }, [handleEvent])

  // Sync theme store with whatever class is already on <html>
  // (set by the inline script in index.html before React mounts)
  useEffect(() => {
    try {
      const saved = localStorage.getItem("pv-theme") as "dark" | "light" | null
      const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? true
      const initial: "dark" | "light" = saved ?? (prefersDark ? "dark" : "light")
      setTheme(initial)
      if (initial === "dark") document.documentElement.classList.add("dark")
      else document.documentElement.classList.remove("dark")
    } catch {
      setTheme("dark")
      document.documentElement.classList.add("dark")
    }
  }, [setTheme])

  // On load, check for incomplete sessions and load saved settings
  useEffect(() => {
    waitForApi().then(async () => {
      const [sessions, settings] = await Promise.all([
        api.getIncompleteSessions(),
        api.getSettings(),
      ])

      if (sessions.ok && sessions.sessions && sessions.sessions.length > 0) {
        setResumeSession(sessions.sessions[0])
      }

      if (settings.ok && settings.last_destination) {
        useAppStore.getState().setDestination(settings.last_destination)
      }

      if (settings.ok && settings.last_date_range) {
        const [start, end] = settings.last_date_range
        useAppStore.getState().setDateRange(start, end)
      }
    })
  }, [])

  return (
    <div className="h-full w-full bg-bg overflow-hidden">
      <ThemeToggle />
      <AnimatePresence mode="wait">
        <motion.div key={screen} className="h-full w-full" {...SLIDE}>
          {screen === "connect" && <ConnectScreen />}
          {screen === "destination" && <DestinationScreen />}
          {screen === "dates" && <DatesScreen />}
          {screen === "summary" && <SummaryScreen />}
          {screen === "progress" && <ProgressScreen />}
          {screen === "complete" && <CompleteScreen />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
