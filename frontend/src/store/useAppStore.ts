import { create } from "zustand"
import type {
  Screen,
  DeviceState,
  ScanState,
  DeviceInfo,
  PhotoAsset,
  AssetStats,
  ScanProgress,
  TransferProgress,
  TransferResults,
  IncompleteSession,
  DeleteProgress,
  DeleteResults,
} from "../lib/types"

interface AppState {
  // Theme
  theme: "dark" | "light"
  setTheme: (t: "dark" | "light") => void

  // Navigation
  screen: Screen

  // Device
  deviceState: DeviceState
  device: DeviceInfo | null
  deviceError: string | null
  needsTunnel: boolean

  // Destination
  destination: string | null

  // Date range
  dateRange: { start: string; end: string } | null

  // Assets from scan
  assets: PhotoAsset[]
  assetStats: AssetStats | null
  scanState: ScanState
  scanProgress: ScanProgress | null
  scanError: string | null

  // Transfer
  transferSessionId: string | null
  safeMode: boolean
  transferProgress: TransferProgress | null
  transferResults: TransferResults | null
  transferError: string | null
  transferPaused: boolean
  deviceSleeping: boolean
  deviceSleepRetryIn: number

  // Delete
  deleteProgress: DeleteProgress | null
  deleteResults: DeleteResults | null

  // Manage Storage
  manageStorageAssets: PhotoAsset[]
  manageStorageStats: AssetStats | null
  manageStorageFilter: "all" | "photos" | "videos" | "screenshots"
  manageStorageScanState: ScanState
  manageStorageScanProgress: ScanProgress | null
  manageStorageScanError: string | null
  manageStorageSelectedIds: Set<string>
  manageStorageViewMode: "grid" | "duplicates" | "analyzer" | "categories"

  // Resume
  resumeSession: IncompleteSession | null

  // Actions
  navigate: (screen: Screen) => void
  setDestination: (path: string) => void
  setDateRange: (start: string, end: string) => void
  setSafeMode: (v: boolean) => void
  setTransferSessionId: (id: string) => void
  setResumeSession: (s: IncompleteSession | null) => void
  clearTransfer: () => void
  handleEvent: (event: string, data: unknown) => void

  // Manage Storage Actions
  setManageStorageFilter: (filter: "all" | "photos" | "videos" | "screenshots") => void
  setManageStorageViewMode: (mode: "grid" | "duplicates" | "analyzer" | "categories") => void
  toggleManageStorageSelection: (id: string) => void
  selectAllManageStorage: () => void
  clearManageStorageSelection: () => void
  clearManageStorage: () => void
}

export const useAppStore = create<AppState>((set) => ({
  theme: "dark",
  setTheme: (t) => set({ theme: t }),

  screen: "connect",

  deviceState: "disconnected",
  device: null,
  deviceError: null,
  needsTunnel: false,

  destination: null,

  dateRange: null,

  assets: [],
  assetStats: null,
  scanState: "idle",
  scanProgress: null,
  scanError: null,

  transferSessionId: null,
  safeMode: true,
  transferProgress: null,
  transferResults: null,
  transferError: null,
  transferPaused: false,
  deviceSleeping: false,
  deviceSleepRetryIn: 0,

  deleteProgress: null,
  deleteResults: null,

  // Manage Storage
  manageStorageAssets: [],
  manageStorageStats: null,
  manageStorageFilter: "all",
  manageStorageScanState: "idle",
  manageStorageScanProgress: null,
  manageStorageScanError: null,
  manageStorageSelectedIds: new Set(),
  manageStorageViewMode: "grid",

  resumeSession: null,

  navigate: (screen) => set({ screen }),

  setDestination: (path) => set({ destination: path }),

  setDateRange: (start, end) => set({ dateRange: { start, end } }),

  setSafeMode: (v) => set({ safeMode: v }),

  setTransferSessionId: (id) => set({ transferSessionId: id }),

  setResumeSession: (s) => set({ resumeSession: s }),

  clearTransfer: () =>
    set({
      transferProgress: null,
      transferResults: null,
      transferError: null,
      transferPaused: false,
      deviceSleeping: false,
      transferSessionId: null,
    }),

  handleEvent: (event, data) => {
    const d = data as Record<string, unknown>

    switch (event) {
      // ── Device ──────────────────────────────────────────────────────
      case "device:connecting":
        // Don't overwrite an already-connected state — a stale poll may fire
        // connect_device() while the ping monitor is already watching
        set((s) =>
          s.deviceState === "connected"
            ? {}
            : { deviceState: "connecting", deviceError: null, needsTunnel: false }
        )
        break

      case "device:connected":
        set({
          deviceState: "connected",
          device: {
            model: d.model as string,
            ios_version: d.ios_version as string,
            total_count: d.total_count as number,
          },
          deviceError: null,
          needsTunnel: false,
        })
        break

      case "device:error":
        // Don't overwrite connected state — a stale poll may return an error
        // after the device is already successfully connected
        set((s) =>
          s.deviceState === "connected"
            ? {}
            : { deviceState: "error", deviceError: d.message as string }
        )
        break

      case "device:needs_tunnel":
        set({ deviceState: "needs_tunnel", needsTunnel: true })
        break

      case "device:disconnected":
        set({
          deviceState: "disconnected",
          device: null,
          assets: [],
          assetStats: null,
          scanState: "idle",
        })
        break

      case "tunnel:started":
        // Tunnel launched; connect_device() will be called again by ConnectScreen
        break

      // ── Scan ─────────────────────────────────────────────────────────
      case "scan:db_progress":
        set({
          scanState: "scanning",
          scanProgress: {
            phase: "db",
            pct: d.pct as number,
            read_mb: d.read_mb as number,
            total_mb: d.total_mb as number,
            eta_seconds: d.eta_seconds as number | null,
          },
        })
        break

      case "scan:progress":
        set({
          scanState: "scanning",
          scanProgress: {
            phase: "exif",
            pct: d.pct as number,
            current: d.current as number,
            total: d.total as number,
          },
        })
        break

      case "scan:complete": {
        const stats: AssetStats = {
          count: d.count as number,
          photos: d.photos as number,
          videos: d.videos as number,
          screenshots: d.screenshots as number,
          total_bytes: d.total_bytes as number,
          total_size_human: d.total_size_human as string,
          stubs: d.stubs as number,
        }
        set({
          scanState: "done",
          scanProgress: null,
          assets: d.assets as PhotoAsset[],
          assetStats: stats,
          scanError: null,
        })
        break
      }

      case "scan:error":
        set({ scanState: "error", scanProgress: null, scanError: d.message as string })
        break

      case "scan:reset":
        set({
          scanState: "idle",
          scanProgress: null,
          scanError: null,
          assets: [],
          assetStats: null,
        })
        break

      // ── Transfer ──────────────────────────────────────────────────────
      case "transfer:progress":
        set({ transferProgress: d as unknown as TransferProgress })
        break

      case "transfer:sleeping":
        set({ deviceSleeping: true, deviceSleepRetryIn: d.retry_in_seconds as number })
        break

      case "transfer:resumed":
        set({ deviceSleeping: false })
        break

      case "transfer:paused":
        set({ transferPaused: true })
        break

      case "transfer:resumed_user":
        set({ transferPaused: false })
        break

      case "transfer:cancelled":
        set({ screen: "connect" })
        break

      case "transfer:complete":
        set({
          transferResults: d as unknown as TransferResults,
          transferProgress: null,
          deviceSleeping: false,
          screen: "complete",
        })
        break

      case "transfer:error":
        set({ transferError: d.message as string })
        break

      // ── Delete ────────────────────────────────────────────────────────
      case "delete:progress":
        set({ deleteProgress: d as unknown as DeleteProgress })
        break

      case "delete:complete":
        set({ deleteResults: d as unknown as DeleteResults, deleteProgress: null })
        break
    }
  },
}))
