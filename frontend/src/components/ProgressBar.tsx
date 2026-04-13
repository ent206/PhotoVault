interface Props {
  pct: number        // 0–1
  glow?: boolean
  height?: string
}

export default function ProgressBar({ pct, glow = false, height = "h-[3px]" }: Props) {
  const width = `${Math.min(100, Math.max(0, pct * 100)).toFixed(2)}%`
  return (
    <div className={`w-full ${height} bg-white/[0.06] rounded-full overflow-visible`}>
      <div
        className={`${height} bg-amber rounded-full transition-all duration-300 ease-out ${glow ? "progress-glow" : ""}`}
        style={{ width }}
      />
    </div>
  )
}
