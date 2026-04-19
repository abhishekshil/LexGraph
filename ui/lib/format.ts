import { TIER_LABELS } from "@/lib/content";
import type { Answer, QuerySignal, ServiceInfo } from "@/lib/types";

export function splitWithMarkers(text: string): Array<{ kind: "text" | "marker"; value: string }> {
  const output: Array<{ kind: "text" | "marker"; value: string }> = [];
  const markerPattern = /\[S(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = markerPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      output.push({ kind: "text", value: text.slice(lastIndex, match.index) });
    }
    output.push({ kind: "marker", value: `S${match[1]}` });
    lastIndex = markerPattern.lastIndex;
  }

  if (lastIndex < text.length) {
    output.push({ kind: "text", value: text.slice(lastIndex) });
  }

  return output;
}

export function summariseAnswer(answer: Answer) {
  return {
    confidence: answer.confidence,
    insufficient_evidence: answer.insufficient_evidence,
    citations: answer.legal_basis.length,
    private_sources: answer.supporting_private_sources.length,
    conflicts: answer.conflicts.length,
    graph_paths: answer.graph_paths.length,
    chars: answer.answer.length,
  };
}

export function formatElapsed(elapsedMs: number): string {
  if (elapsedMs < 1000) {
    return `${elapsedMs.toFixed(0)} ms`;
  }
  return `${(elapsedMs / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function tierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? "Unknown";
}

export function serviceSearchText(service: ServiceInfo): string {
  return [
    service.id,
    service.title,
    service.kind,
    service.description,
    service.python_module,
    service.compose_service ?? "",
    ...(service.listens ?? []),
    ...(service.publishes ?? []),
  ]
    .join(" ")
    .toLowerCase();
}

export function deriveQuerySignals(question: string, matterScope: string): QuerySignal[] {
  const text = question.toLowerCase();
  const signals: QuerySignal[] = [];

  if (matterScope.trim()) {
    signals.push({ label: "Matter-scoped retrieval", tone: "accent" });
  }

  if (/\bsection\s+\d+\b/.test(text) || /\b(ipc|crpc|iea|bns|bnss|bsa)\b/.test(text)) {
    signals.push({ label: "Statute anchor detected", tone: "accent" });
  }

  if (/\bpunishment|sentence|penalty|imprisonment\b/.test(text)) {
    signals.push({ label: "Punishment lookup", tone: "neutral" });
  }

  if (/\b(map|crosswalk|equivalent)\b/.test(text) || (/\bipc\b/.test(text) && /\bbns\b/.test(text))) {
    signals.push({ label: "Crosswalk-sensitive question", tone: "warn" });
  }

  if (/\bversus\b|\bv\.\b|\bcitation\b|\bjudgment\b|\bprecedent\b/.test(text)) {
    signals.push({ label: "Precedent retrieval likely", tone: "neutral" });
  }

  if (signals.length === 0) {
    signals.push({ label: "Generic research query", tone: "neutral" });
  }

  return signals.slice(0, 4);
}
