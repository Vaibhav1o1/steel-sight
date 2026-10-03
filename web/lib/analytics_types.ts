export interface StatusSeriesBucket {
  bucket_id: string;
  label: string;
  ts_start: string | null;
  ts_end: string | null;
  pass_count: number;
  rework_count: number;
  fail_count: number;
  review_count: number;
  total_count: number;
  evaluated_count: number;
  nonconforming_count: number;
  p_rate: number | null;
  ucl: number | null;
  lcl: number | null;
  centerline: number | null;
  reliable: boolean;
}

export interface StatusSeriesResponse {
  mode: "count" | "time";
  basis: "final" | "auto";
  source_filter: "all" | "synthetic" | "real";
  buckets: StatusSeriesBucket[];
  total_inspections: number;
  total_evaluated: number;
  total_nonconforming: number;
  overall_p_bar: number | null;
  pass_count: number;
  rework_count: number;
  fail_count: number;
  review_count: number;
  has_synthetic: boolean;
}

export interface StatusSeriesParams {
  mode?: "count" | "time";
  basis?: "final" | "auto";
  source?: "all" | "synthetic" | "real";
  bucket_size?: number;
  interval?: string;
  since?: string;
}
