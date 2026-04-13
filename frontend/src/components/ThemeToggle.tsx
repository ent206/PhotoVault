import { useAppStore } from "../store/useAppStore"

export default function ThemeToggle() {
  const theme   = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)

  function toggle() {
    const next: "dark" | "light" = theme === "dark" ? "light" : "dark"

    // Brief transition class for smooth color shift
    document.documentElement.classList.add("theme-transitioning")
    setTimeout(() => document.documentElement.classList.remove("theme-transitioning"), 300)

    if (next === "dark") {
      document.documentElement.classList.add("dark")
    } else {
      document.documentElement.classList.remove("dark")
    }

    try { localStorage.setItem("pv-theme", next) } catch { /* file:// may block */ }
    setTheme(next)
  }

  return (
    <button
      onClick={toggle}
      className="fixed bottom-4 right-4 z-50 w-8 h-8 flex items-center justify-center
                 rounded-full border border-border bg-card text-muted
                 hover:text-text hover:border-border-hi transition-all duration-150
                 active:scale-95"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  )
}
