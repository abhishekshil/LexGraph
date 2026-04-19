import type {
  ArchitectureLane,
  DeliveryMetric,
  IngestKind,
  ModeOption,
  ResearchPrompt,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080/api";

export const TIER_LABELS: Record<number, string> = {
  1: "Constitution / Statute",
  2: "Supreme Court",
  3: "High Court",
  4: "Tribunal",
  5: "Lower Court",
  6: "Private Document",
  7: "Private Note",
  8: "AI Summary",
};

export const QUERY_MODES: ModeOption[] = [
  {
    value: "graph_only",
    label: "Graph only",
    detail: "Strict structural retrieval. Best when you know the section, case, or graph path you want.",
  },
  {
    value: "graph_plus_semantic",
    label: "Graph + semantic",
    detail: "Default v1 mode. Graph traversal first, semantic recall only when the graph needs help.",
  },
  {
    value: "graph_plus_semantic_plus_rerank",
    label: "Graph + semantic + rerank",
    detail: "Highest recall mode with composite reranking for harder legal questions.",
  },
];

export const SAMPLE_PROMPTS: ResearchPrompt[] = [
  {
    label: "Theft ingredients",
    question: "What are the ingredients of theft under Section 378 IPC?",
  },
  {
    label: "Punishment lookup",
    question: "What is the punishment for theft under Section 379 IPC?",
  },
  {
    label: "Crosswalk check",
    question: "Map the old IPC theft provision to its BNS equivalent and explain whether the ingredients changed.",
  },
  {
    label: "Matter-scoped query",
    question: "Using the private matter materials, identify contradictions in the witness narrative on possession and consent.",
    matterId: "matter-001",
  },
];

export const ARCHITECTURE_LANES: ArchitectureLane[] = [
  {
    status: "implemented",
    title: "Research engine is the v1 product",
    summary: "Ingestion, graph retrieval, evidence packs, grounded answers, and evaluation already exist in the repo.",
    points: [
      "Graph-first retrieval with semantic fallback",
      "Evidence-locked answer generation",
      "Matter-scoped private document handling",
    ],
  },
  {
    status: "partial",
    title: "Workflow exists as runtime orchestration",
    summary: "FastAPI plus worker streams and live trace events form the current workflow layer.",
    points: [
      "Streaming trace for every research request",
      "Independent worker boundaries per service",
      "Operational visibility through service discovery",
    ],
  },
  {
    status: "planned",
    title: "Drafting remains a deliberate v2 lane",
    summary: "Templates, approval gates, and document assembly should land only after research reliability is stable.",
    points: [
      "No drafting engine claim in v1",
      "No fake collaboration surface",
      "Roadmap stays aligned with the shared platform",
    ],
  },
];

export const DELIVERY_METRICS: DeliveryMetric[] = [
  { label: "Current scope", value: "Research-first v1" },
  { label: "Services", value: "9 discoverable runtimes" },
  { label: "Guarantee", value: "No source, no answer" },
];

export const V1_CHECKLIST = [
  "Keep the UI honest about implemented versus planned scope.",
  "Treat the graph as primary memory and vectors as fallback only.",
  "Make ingestion, querying, and runtime health visible in one workspace.",
  "Preserve refusal behavior when the evidence pack is weak.",
];

export const INGEST_KINDS: IngestKind[] = [
  { value: "generic", label: "Generic" },
  { value: "statute", label: "Statute" },
  { value: "judgment", label: "Judgment" },
  { value: "fir", label: "FIR" },
  { value: "chargesheet", label: "Chargesheet" },
  { value: "witness_statement", label: "Witness Statement" },
  { value: "contract", label: "Contract" },
  { value: "notice", label: "Notice" },
  { value: "memo", label: "Memo" },
];
