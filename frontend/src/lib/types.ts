// TypeScript types mirroring Python models

export interface DeviceInfo {
  model: string
  ios_version: string
  total_count: number
}

export interface PhotoAsset {
  id: string               // = source_path, used to reference back to Python
  filename: string
  source_path: string
  date_taken: string       // ISO string
  file_size: number
  media_type: "photo" | "video" | "live_photo_image" | "live_photo_video"
  live_photo_pair_id: string | null
  is_icloud_stub: boolean
  is_screenshot: boolean
}

export interface AssetStats {
  count: number
  photos: number
  videos: number
  screenshots: number
  total_bytes: number
  total_size_human: string
  stubs: number
}

export interface DriveInfo {
  name: string
  path: string
  free_bytes: number
  total_bytes: number
  free_human: string
  total_human: string
  is_external: boolean
}

export interface ScanProgress {
  phase: "db" | "exif"
  pct: number
  read_mb?: number
  total_mb?: number
  eta_seconds?: number | null
  current?: number
  total?: number
}

export interface TransferProgress {
  current_filename: string
  files_done: number
  files_total: number
  bytes_done: number
  bytes_total: number
  pct: number
  speed_mbps: number
  eta_seconds: number
}

export interface TransferResults {
  completed: number
  skipped: number
  failed: number
  failed_files: string[]
}

export interface IncompleteSession {
  session_id: string
  started_at: string
  source_device: string
  destination_path: string
  completed_count: number
  total_files: number
}

export interface TransferSummary {
  photos: number
  videos: number
  total_bytes: number
  total_size_human: string
  duplicates: number
  stubs: number
  space_ok: boolean
  free_bytes: number
  free_human: string
  headroom_pct: number
  eta_seconds: number
}

export interface DeleteProgress {
  done: number
  total: number
  deleted: number
  failed: number
  freed_bytes: number
  freed_human: string
  pct: number
}

export interface DeleteResults {
  deleted: number
  failed: number
  freed_bytes: number
  freed_human: string
}

export type Screen =
  | "connect"
  | "destination"
  | "dates"
  | "summary"
  | "progress"
  | "complete"

export type ScanState = "idle" | "scanning" | "done" | "error"
export type DeviceState = "disconnected" | "connecting" | "connected" | "needs_tunnel" | "error"
