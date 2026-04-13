// Typed wrappers for window.pywebview.api.*
// All methods return {ok: boolean, ...} from Python.

declare global {
  interface Window {
    pywebview: {
      api: PyWebViewAPI
    }
    __pv: (payload: { event: string; data: unknown }) => void
  }
}

interface PyWebViewAPI {
  // Connection
  connect_device(): Promise<{ ok: boolean; status?: string }>
  start_tunnel(password: string): Promise<{ ok: boolean; error?: string }>

  // Destination
  list_drives(): Promise<{
    ok: boolean
    drives?: import("./types").DriveInfo[]
    recent_destinations?: string[]
    error?: string
  }>
  browse_folder(): Promise<{ ok: boolean; path?: string | null; error?: string }>
  set_destination(
    path: string,
    subfolder?: string
  ): Promise<{ ok: boolean; resolved_path?: string; error?: string }>
  check_space(
    path: string,
    required_bytes: number
  ): Promise<{ ok: boolean; ok_space?: boolean; free_bytes?: number; free_human?: string; headroom_pct?: number; error?: string }>

  // Scan
  get_saved_date_range(): Promise<{ ok: boolean; start?: string | null; end?: string | null }>
  start_scan(start_iso: string, end_iso: string): Promise<{ ok: boolean; status?: string; error?: string }>
  list_assets(
    start_iso: string,
    end_iso: string
  ): Promise<{ ok: boolean; count?: number; assets?: import("./types").PhotoAsset[]; error?: string }>

  // Summary
  get_transfer_summary(
    asset_ids: string[],
    destination: string
  ): Promise<{ ok: boolean } & Partial<import("./types").TransferSummary> & { error?: string }>

  // Transfer
  start_transfer(
    asset_ids: string[],
    destination: string,
    safe_mode: boolean,
    session_id?: string
  ): Promise<{ ok: boolean; session_id?: string; error?: string }>
  pause_transfer(): Promise<{ ok: boolean; error?: string }>
  resume_transfer(): Promise<{ ok: boolean; error?: string }>
  cancel_transfer(): Promise<{ ok: boolean; error?: string }>

  // Sessions
  get_incomplete_sessions(): Promise<{
    ok: boolean
    sessions?: import("./types").IncompleteSession[]
    error?: string
  }>
  dismiss_session(session_id: string): Promise<{ ok: boolean; error?: string }>

  // Delete
  start_delete(
    asset_ids: string[],
    destination: string
  ): Promise<{ ok: boolean; total?: number; error?: string }>

  // Settings
  get_settings(): Promise<{
    ok: boolean
    last_destination?: string | null
    recent_destinations?: string[]
    last_date_range?: [string, string] | null
    error?: string
  }>
}

// Helper: wait for pywebview.api to be available (it injects asynchronously)
export function waitForApi(): Promise<PyWebViewAPI> {
  return new Promise((resolve) => {
    const check = () => {
      if (window.pywebview?.api) {
        resolve(window.pywebview.api)
      } else {
        setTimeout(check, 50)
      }
    }
    check()
  })
}

export const api = {
  async call<T>(fn: () => Promise<T>): Promise<T> {
    await waitForApi()
    return fn()
  },

  connectDevice: () => window.pywebview.api.connect_device(),
  startTunnel: (pw: string) => window.pywebview.api.start_tunnel(pw),

  listDrives: () => window.pywebview.api.list_drives(),
  browseFolder: () => window.pywebview.api.browse_folder(),
  setDestination: (path: string, subfolder = "") =>
    window.pywebview.api.set_destination(path, subfolder),
  checkSpace: (path: string, bytes: number) =>
    window.pywebview.api.check_space(path, bytes),

  getSavedDateRange: () => window.pywebview.api.get_saved_date_range(),
  startScan: (start: string, end: string) => window.pywebview.api.start_scan(start, end),
  listAssets: (start: string, end: string) => window.pywebview.api.list_assets(start, end),

  getTransferSummary: (ids: string[], dest: string) =>
    window.pywebview.api.get_transfer_summary(ids, dest),

  startTransfer: (ids: string[], dest: string, safeMode: boolean, sessionId?: string) =>
    window.pywebview.api.start_transfer(ids, dest, safeMode, sessionId),
  pauseTransfer: () => window.pywebview.api.pause_transfer(),
  resumeTransfer: () => window.pywebview.api.resume_transfer(),
  cancelTransfer: () => window.pywebview.api.cancel_transfer(),

  getIncompleteSessions: () => window.pywebview.api.get_incomplete_sessions(),
  dismissSession: (id: string) => window.pywebview.api.dismiss_session(id),

  startDelete: (ids: string[], dest: string) =>
    window.pywebview.api.start_delete(ids, dest),

  getSettings: () => window.pywebview.api.get_settings(),
}
