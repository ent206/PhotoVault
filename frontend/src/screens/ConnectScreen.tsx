import { useEffect, useRef, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { useAppStore } from "../store/useAppStore"
import { api, waitForApi } from "../lib/api"
import ResumeModal from "../components/ResumeModal"

export default function ConnectScreen() {
  const deviceState = useAppStore((s) => s.deviceState)
  const device = useAppStore((s) => s.device)
  const deviceError = useAppStore((s) => s.deviceError)
  const needsTunnel = useAppStore((s) => s.needsTunnel)
  const resumeSession = useAppStore((s) => s.resumeSession)
  const navigate = useAppStore((s) => s.navigate)

  const [tunnelPassword, setTunnelPassword] = useState("")
  const [tunnelOpen, setTunnelOpen] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false
    async function startPolling() {
      await waitForApi()
      if (cancelled) return
      api.connectDevice()
      // Fast polling for quick connect detection (800ms)
      pollingRef.current = setInterval(() => {
        const state = useAppStore.getState().deviceState
        if (state !== "connected") api.connectDevice()
      }, 800)
    }
    startPolling()
    return () => {
      cancelled = true
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  useEffect(() => {
    if (deviceState === "connected" && pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    if (deviceState === "disconnected" && !pollingRef.current) {
      api.connectDevice() // Immediate check
      pollingRef.current = setInterval(() => api.connectDevice(), 800)
    }
  }, [deviceState])

  useEffect(() => {
    if (needsTunnel) setTunnelOpen(true)
  }, [needsTunnel])

  const [isRetrying, setIsRetrying] = useState(false)

  async function handleStartTunnel() {
    if (!tunnelPassword.trim()) return
    await api.startTunnel(tunnelPassword)
    setTunnelOpen(false)
    setTunnelPassword("")
    setTimeout(() => api.connectDevice(), 1500)
  }

  async function handleRetry() {
    setIsRetrying(true)
    await api.connectDevice()
    // Reset after a short delay to show the user something happened
    setTimeout(() => setIsRetrying(false), 2000)
  }

  const isConnected = deviceState === "connected"
  // "error" is also a waiting state — polling continues and we retry automatically
  const isWaiting   = deviceState === "disconnected" || deviceState === "connecting" || deviceState === "error"

  return (
    <div className="screen items-center justify-center relative">
      <AnimatePresence>
        {resumeSession && <ResumeModal session={resumeSession} />}
      </AnimatePresence>

      {/* Atmospheric center glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: isConnected
            ? "radial-gradient(ellipse 60% 55% at 50% 42%, rgba(212,146,74,0.1) 0%, transparent 70%)"
            : "radial-gradient(ellipse 50% 45% at 50% 42%, rgba(212,146,74,0.04) 0%, transparent 70%)",
          transition: "background 1.2s ease",
        }}
      />

      <motion.div
        className="flex flex-col items-center max-w-xs w-full px-6 relative z-10"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } }}
      >
        {/* Wordmark */}
        <div className="mb-14 text-center">
          <p className="label-xs mb-3 tracking-[0.3em]">PhotoVault</p>
          <h1 className="font-display text-display-xl text-text font-light leading-none">
            iPhone<br />
            <span className="italic text-amber/90">Transfer</span>
          </h1>
        </div>

        {/* Phone icon with halo */}
        <div className="relative mb-12 flex items-center justify-center">
          {/* Ping rings — only while waiting */}
          {isWaiting && (
            <>
              <span
                className="amber-ping absolute rounded-full border border-amber/20"
                style={{ width: 96, height: 96 }}
              />
              <span
                className="amber-ping absolute rounded-full border border-amber/12"
                style={{ width: 96, height: 96, animationDelay: "0.9s" }}
              />
            </>
          )}

          {/* Icon container */}
          <div className={`relative ${isWaiting ? "phone-breathing" : ""}`}>
            {/* Glow behind icon */}
            <div
              className="absolute inset-0 rounded-full blur-xl transition-opacity duration-1000"
              style={{
                background: "rgba(212,146,74,0.3)",
                opacity: isConnected ? 0.9 : 0.25,
                transform: "scale(1.4)",
              }}
            />
            <PhoneIcon connected={isConnected} error={deviceState === "error"} />
          </div>
        </div>

        {/* Status text */}
        <div className="text-center mb-10 min-h-[48px] flex flex-col items-center justify-center">
          <AnimatePresence mode="wait">
            <motion.div
              key={deviceState + (device?.model ?? "")}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.25 } }}
              exit={{ opacity: 0, y: -5, transition: { duration: 0.15 } }}
              className="text-center"
            >
              {isConnected && device && (
                <>
                  <p className="text-success font-sans text-sm font-medium mb-0.5">
                    Connected
                  </p>
                  <p className="font-display text-xl text-text font-light">
                    {device.model}
                  </p>
                  <p className="text-xs text-muted font-mono mt-1">iOS {device.ios_version}</p>
                </>
              )}
              {(deviceState === "disconnected" || deviceState === "connecting") && (
                <p className="text-sm text-muted font-sans">
                  {deviceState === "connecting" ? "Connecting…" : "Connect iPhone to begin"}
                </p>
              )}
              {deviceState === "error" && (
                <>
                  <p className="text-sm text-danger font-sans text-center max-w-[220px]">{deviceError ?? "Connection failed"}</p>
                  <p className="text-xs text-muted font-sans mt-1 mb-3">
                    Tap "Trust" on your iPhone when prompted, then click Retry
                  </p>
                  <button
                    onClick={handleRetry}
                    disabled={isRetrying}
                    className="px-4 py-2 rounded-lg bg-amber/20 hover:bg-amber/30 disabled:opacity-50 text-amber text-sm font-medium transition-colors min-w-[140px]"
                  >
                    {isRetrying ? "Retrying…" : "Retry Connection"}
                  </button>
                </>
              )}
              {deviceState === "needs_tunnel" && (
                <p className="text-sm text-warn font-sans">iOS 17+ tunnel required</p>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Waiting dots */}
          {isWaiting && (
            <div className="flex items-center gap-1.5 mt-4">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="block w-1 h-1 rounded-full bg-amber/40"
                  animate={{ opacity: [0.25, 0.85, 0.25] }}
                  transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.22 }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <AnimatePresence>
          {isConnected && (
            <motion.div
              className="flex flex-col gap-3 w-full"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.3 } }}
              exit={{ opacity: 0 }}
            >
              <button
                className="btn-amber w-full py-3 text-sm tracking-wide"
                onClick={() => navigate("destination")}
              >
                Transfer Files
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
              </button>
              <button
                className="btn-secondary w-full py-3 text-sm tracking-wide"
                onClick={() => navigate("manage_storage")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18M3 12h18M3 18h18"/>
                </svg>
                Manage Storage
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Tunnel panel */}
        <AnimatePresence>
          {(needsTunnel || tunnelOpen) && (
            <motion.div
              className="w-full mt-5 rounded-xl border border-warn/20 bg-warn/[0.06] p-5 overflow-hidden"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <p className="label-xs text-warn mb-1">iOS 17+ Tunnel Required</p>
              <p className="text-xs text-muted font-sans mb-4 leading-relaxed">
                Enter your Mac password to start a one-time background tunnel.
              </p>
              <input
                type="password"
                placeholder="Mac password"
                value={tunnelPassword}
                onChange={(e) => setTunnelPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleStartTunnel()}
                className="field mb-3 text-sm"
              />
              <button
                className="btn-amber w-full text-sm py-2.5"
                onClick={handleStartTunnel}
                disabled={!tunnelPassword.trim()}
              >
                Start Tunnel
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}

function PhoneIcon({ connected, error }: { connected: boolean; error: boolean }) {
  const stroke = error ? "#c95555" : connected ? "#d4924a" : "#4a4540"
  return (
    <svg
      width="56" height="56"
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth="1.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ transition: "stroke 0.8s ease", position: "relative", zIndex: 1 }}
    >
      <rect x="5" y="2" width="14" height="20" rx="2" />
      <line x1="12" y1="18" x2="12.01" y2="18" strokeWidth="2" />
    </svg>
  )
}
