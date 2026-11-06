// Shapes of the published JSON (store/publish.py, store/points.py; DECISIONS.md D52, D57).

export interface BlockMeta { start_utc: string; end_utc: string; app_day: string; label: string }
export interface DayMeta { app_day: string; label: string }
export interface LayerMeta { file: string; dtype: "u8" | "u16"; shape: number[]; missing: number }
export interface Grid { lat_first: number; lon_first: number; step_deg: number; n_lat: number; n_lon: number }

export interface Meta {
  run_id: string;
  run_time_utc: string;
  previous_run_id: string | null;
  processed_at_utc: string;
  members_per_model: number;
  event_mm: number;
  grid: Grid;
  tile_cells: number;
  summary_start_blocks: number;
  stale_after_h?: number;
  blocks: BlockMeta[];
  days: DayMeta[];
  layers: Record<string, LayerMeta>;
}

// cell.b[k] = [n_ifs, n_aifs, n_prev|-1, dots, p10, p90, median_ifs, median_aifs]
export type BlockRow = [number, number, number, string, number, number, number, number];
export interface Cell { b: BlockRow[]; bt: [number, number][]; d: number[][]; dt: [number, number][]; s: number[] }
export interface Tile { run: string; tile: [number, number]; strings: string[]; cells: Record<string, Cell> }
