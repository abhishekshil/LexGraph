"use client";

import {
  ARCHITECTURE_LANES,
  INGEST_KINDS,
  QUERY_MODES,
  SAMPLE_PROMPTS,
  TIER_LABELS,
  V1_CHECKLIST,
} from "@/lib/content";
import { formatBytes } from "@/lib/format";
import type {
  QueryMode,
  QuerySignal,
  ServiceInfo,
  UploadResponse,
} from "@/lib/types";

type QueryConsoleProps = {
  question: string;
  matterScope: string;
  mode: QueryMode;
  loading: boolean;
  signals: QuerySignal[];
  onQuestionChange: (value: string) => void;
  onMatterScopeChange: (value: string) => void;
  onModeChange: (value: QueryMode) => void;
  onAsk: () => void;
  onCancel: () => void;
};

type UploadPanelProps = {
  matterId: string;
  kind: string;
  fileName: string;
  uploadResult: UploadResponse | null;
  loading: boolean;
  error: string | null;
  onMatterIdChange: (value: string) => void;
  onKindChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: () => void;
};

type RuntimePanelProps = {
  services: ServiceInfo[];
  loading: boolean;
  error: string | null;
  filter: string;
  apiBase: string;
  onFilterChange: (value: string) => void;
  onRefresh: () => void;
};

export function QueryConsole({
  question,
  matterScope,
  mode,
  loading,
  signals,
  onQuestionChange,
  onMatterScopeChange,
  onModeChange,
  onAsk,
  onCancel,
}: QueryConsoleProps) {
  return (
    <section id="research-console" className="workspace-panel research-panel">
      <div className="section-heading section-heading-wide">
        <div>
          <p className="section-kicker">Research console</p>
          <h2>Run a grounded legal query</h2>
        </div>
        <div className="answer-stats">
          <span className="stat-pill">3 retrieval modes</span>
          <span className="stat-pill">SSE trace</span>
        </div>
      </div>

      <textarea
        className="question-input"
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        placeholder="Ask a section, precedent, crosswalk, contradiction, or matter-scoped question."
      />

      <div className="signal-row">
        {signals.map((signal) => (
          <span key={signal.label} className={`signal-pill signal-${signal.tone}`}>
            {signal.label}
          </span>
        ))}
      </div>

      <div className="field-grid">
        <label className="field">
          <span className="field-label">Matter scope</span>
          <input
            value={matterScope}
            onChange={(event) => onMatterScopeChange(event.target.value)}
            placeholder="Optional. Keeps retrieval inside private matter material."
          />
        </label>
      </div>

      <div className="mode-switch" role="tablist" aria-label="Retrieval mode">
        {QUERY_MODES.map((option) => (
          <button
            key={option.value}
            type="button"
            className={option.value === mode ? "mode-option is-active" : "mode-option"}
            onClick={() => onModeChange(option.value)}
          >
            <strong>{option.label}</strong>
            <span>{option.detail}</span>
          </button>
        ))}
      </div>

      <div className="panel-action-row">
        <div className="sample-strip" aria-label="Sample prompts">
          {SAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt.label}
              type="button"
              className="sample-chip"
              onClick={() => {
                onQuestionChange(prompt.question);
                onMatterScopeChange(prompt.matterId ?? "");
              }}
            >
              {prompt.label}
            </button>
          ))}
        </div>
        <div className="action-group">
          {loading ? (
            <button type="button" className="secondary-button" onClick={onCancel}>
              Stop stream
            </button>
          ) : null}
          <button type="button" className="primary-button" onClick={onAsk} disabled={!question.trim() || loading}>
            {loading ? "Running query..." : "Run research"}
          </button>
        </div>
      </div>

      <div className="legend">
        {Object.entries(TIER_LABELS).map(([tier, label]) => (
          <span key={tier} className={`tier-pill tier-${tier}`}>
            tier {tier}: {label}
          </span>
        ))}
      </div>
    </section>
  );
}

export function ArchitecturePanel() {
  return (
    <section className="workspace-panel architecture-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Architecture status</p>
          <h2>Working in the right direction</h2>
        </div>
      </div>

      <div className="stack-list">
        {ARCHITECTURE_LANES.map((lane) => (
          <article key={lane.title} className={`stack-item stack-item-${lane.status}`}>
            <div className="stack-item-head">
              <span className={`status-badge status-${lane.status}`}>{lane.status}</span>
            </div>
            <h3>{lane.title}</h3>
            <p>{lane.summary}</p>
          </article>
        ))}
      </div>

      <ul className="lane-points">
        {V1_CHECKLIST.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function UploadPanel({
  matterId,
  kind,
  fileName,
  uploadResult,
  loading,
  error,
  onMatterIdChange,
  onKindChange,
  onFileChange,
  onSubmit,
}: UploadPanelProps) {
  return (
    <section className="workspace-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Matter ingest</p>
          <h2>Queue a private document</h2>
        </div>
      </div>

      <div className="field-grid">
        <label className="field">
          <span className="field-label">Matter id</span>
          <input
            value={matterId}
            onChange={(event) => onMatterIdChange(event.target.value)}
            placeholder="Required. Example: matter-001"
          />
        </label>
        <label className="field">
          <span className="field-label">Document kind</span>
          <select value={kind} onChange={(event) => onKindChange(event.target.value)}>
            {INGEST_KINDS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="upload-dropzone">
        <input
          type="file"
          onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
        />
        <span>{fileName || "Choose a file to upload into matter-scoped storage."}</span>
      </label>

      <div className="panel-action-row panel-action-row-compact">
        <button
          type="button"
          className="primary-button"
          onClick={onSubmit}
          disabled={loading || !matterId.trim() || !fileName}
        >
          {loading ? "Queueing..." : "Queue ingest"}
        </button>
      </div>

      {error ? <p className="error-copy">{error}</p> : null}

      {uploadResult ? (
        <div className="upload-result">
          <div>
            <span className="meta-label">Trace</span>
            <code>{uploadResult.trace_id}</code>
          </div>
          <div>
            <span className="meta-label">Storage</span>
            <code>{uploadResult.storage_uri}</code>
          </div>
          <div>
            <span className="meta-label">Payload</span>
            <strong>
              {uploadResult.kind} · {formatBytes(uploadResult.size)}
            </strong>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function RuntimePanel({
  services,
  loading,
  error,
  filter,
  apiBase,
  onFilterChange,
  onRefresh,
}: RuntimePanelProps) {
  return (
    <section id="runtime-panel" className="workspace-panel">
      <div className="section-heading section-heading-wide">
        <div>
          <p className="section-kicker">Runtime topology</p>
          <h2>Service discovery</h2>
        </div>
        <button type="button" className="secondary-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>

      <div className="runtime-meta">
        <span className="stat-pill">API base: {apiBase}</span>
        <span className="stat-pill">{services.length} services loaded</span>
      </div>

      <label className="field">
        <span className="field-label">Filter services</span>
        <input
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
          placeholder="Search by id, module, stream, or description."
        />
      </label>

      {loading ? <p className="muted-text">Loading service catalog…</p> : null}
      {error ? <p className="error-copy">{error}</p> : null}

      <div className="stack-list service-list">
        {services.map((service) => (
          <article key={service.id} className="stack-item service-item">
            <div className="stack-item-head">
              <span className="status-badge status-implemented">{service.kind}</span>
              <strong>{service.title}</strong>
            </div>
            <p>{service.description}</p>
            <div className="service-identity">
              <code>{service.id}</code>
              <code>{service.python_module}</code>
            </div>
            <div className="service-streams">
              {(service.listens ?? []).map((stream) => (
                <span key={`${service.id}-listen-${stream}`} className="stream-pill stream-pill-in">
                  listens: {stream}
                </span>
              ))}
              {(service.publishes ?? []).map((stream) => (
                <span key={`${service.id}-publish-${stream}`} className="stream-pill stream-pill-out">
                  publishes: {stream}
                </span>
              ))}
              {service.public_base_path ? (
                <span className="stream-pill">route: {service.public_base_path}</span>
              ) : null}
            </div>
          </article>
        ))}

        {!loading && services.length === 0 ? (
          <article className="stack-item">
            <p>No services matched the current filter.</p>
          </article>
        ) : null}
      </div>
    </section>
  );
}
