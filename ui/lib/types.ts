export type QueryMode =
  | "graph_only"
  | "graph_plus_semantic"
  | "graph_plus_semantic_plus_rerank";

export type Citation = {
  marker: string;
  type: string;
  title?: string;
  authority?: string;
  court?: string;
  date?: string;
  section_or_paragraph?: string;
  excerpt: string;
  source_id: string;
  source_span_id: string;
  file_id: string;
  chunk_id?: string | null;
  node_id: string;
  tier: number;
  score?: number;
};

export type Conflict = {
  description: string;
  citations: string[];
  severity: string;
};

export type GraphPath = {
  nodes: string[];
  edges: string[];
  narrative: string;
};

export type Answer = {
  question: string;
  query_type: string;
  answer: string;
  legal_basis: Citation[];
  supporting_private_sources: Citation[];
  conflicts: Conflict[];
  confidence: "low" | "medium" | "high";
  insufficient_evidence: boolean;
  graph_paths: GraphPath[];
  notes: string[];
  extras?: Record<string, unknown>;
  evidence_pack_id?: string | null;
  trace_id: string;
};

export type TraceEvent = {
  ts: number;
  stage: string;
  status: "start" | "done" | "info" | "warn" | "error" | "end";
  worker?: string;
  message?: string;
  trace_id?: string;
  details?: Record<string, unknown>;
  answer?: Answer;
  error?: string;
};

export type ServiceInfo = {
  id: string;
  title: string;
  kind: string;
  python_module: string;
  compose_service?: string;
  description: string;
  public_base_path?: string;
  listens?: string[];
  publishes?: string[];
};

export type ServiceCatalog = {
  version: number;
  services: ServiceInfo[];
};

export type UploadResponse = {
  trace_id: string;
  queued: boolean;
  matter_id: string;
  kind: string;
  storage_uri: string;
  sha256: string;
  size: number;
};

export type QuerySignal = {
  label: string;
  tone: "neutral" | "accent" | "warn";
};

export type ModeOption = {
  value: QueryMode;
  label: string;
  detail: string;
};

export type ResearchPrompt = {
  label: string;
  question: string;
  matterId?: string;
};

export type ArchitectureLane = {
  status: "implemented" | "partial" | "planned";
  title: string;
  summary: string;
  points: string[];
};

export type DeliveryMetric = {
  label: string;
  value: string;
};

export type IngestKind = {
  value: string;
  label: string;
};
