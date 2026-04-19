"use client";

import { TIER_LABELS } from "@/lib/content";
import { splitWithMarkers, tierLabel } from "@/lib/format";
import type { Answer, Citation } from "@/lib/types";

type AnswerViewProps = {
  answer: Answer | null;
  error: string | null;
};

export function AnswerView({ answer, error }: AnswerViewProps) {
  if (error) {
    return (
      <section className="workspace-panel answer-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Query status</p>
            <h2>Pipeline error</h2>
          </div>
          <span className="stat-pill stat-pill-danger">attention</span>
        </div>
        <p className="error-copy">{error}</p>
      </section>
    );
  }

  if (!answer) {
    return (
      <section className="workspace-panel answer-panel">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Research output</p>
            <h2>Workspace ready</h2>
          </div>
        </div>
        <div className="empty-state">
          <p>
            Run a query to inspect the grounded answer, citation pack, graph
            paths, and refusal diagnostics in one place.
          </p>
          <div className="legend">
            {Object.entries(TIER_LABELS).map(([tier, label]) => (
              <span key={tier} className={`tier-pill tier-${tier}`}>
                tier {tier}: {label}
              </span>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (answer.insufficient_evidence) {
    return <RefusalView answer={answer} />;
  }

  return (
    <>
      <section className="workspace-panel answer-panel">
        <div className="section-heading section-heading-wide">
          <div>
            <p className="section-kicker">Grounded answer</p>
            <h2>{answer.query_type || "Research result"}</h2>
          </div>
          <div className="answer-stats">
            <span className={`stat-pill confidence-${answer.confidence}`}>
              confidence: {answer.confidence}
            </span>
            <span className="stat-pill">{answer.legal_basis.length} public citations</span>
            <span className="stat-pill">
              {answer.supporting_private_sources.length} private sources
            </span>
          </div>
        </div>

        <div className="answer-summary-grid">
          <div className="answer-body-shell">
            <AnswerBody text={answer.answer} />
          </div>
          <aside className="answer-meta">
            <div>
              <span className="meta-label">Trace</span>
              <code>{answer.trace_id}</code>
            </div>
            {answer.evidence_pack_id ? (
              <div>
                <span className="meta-label">Evidence pack</span>
                <code>{answer.evidence_pack_id}</code>
              </div>
            ) : null}
            {answer.extras?.provider ? (
              <div>
                <span className="meta-label">Model provider</span>
                <strong>{String(answer.extras.provider)}</strong>
              </div>
            ) : null}
          </aside>
        </div>
      </section>

      {answer.conflicts.length > 0 ? (
        <section className="workspace-panel conflict-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Conflict watch</p>
              <h2>Conflicting authorities or signals</h2>
            </div>
          </div>
          <div className="stack-list">
            {answer.conflicts.map((conflict, index) => (
              <article key={`${conflict.description}-${index}`} className="stack-item">
                <div className="stack-item-head">
                  <span className="stat-pill stat-pill-warn">severity: {conflict.severity}</span>
                </div>
                <p>{conflict.description}</p>
                <div className="muted-text">
                  markers: {conflict.citations.map((marker) => `[${marker}]`).join(" ")}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {answer.legal_basis.length > 0 ? (
        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Authority set</p>
              <h2>Public legal basis</h2>
            </div>
          </div>
          <div className="stack-list">
            {answer.legal_basis.map((citation) => (
              <CitationCard key={citation.marker} citation={citation} kind="public" />
            ))}
          </div>
        </section>
      ) : null}

      {answer.supporting_private_sources.length > 0 ? (
        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Matter evidence</p>
              <h2>Private case material</h2>
            </div>
          </div>
          <div className="stack-list">
            {answer.supporting_private_sources.map((citation) => (
              <CitationCard key={citation.marker} citation={citation} kind="private" />
            ))}
          </div>
        </section>
      ) : null}

      {answer.graph_paths.length > 0 ? (
        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Reasoning route</p>
              <h2>Graph paths</h2>
            </div>
          </div>
          <div className="stack-list">
            {answer.graph_paths.map((path, index) => (
              <article key={`${path.narrative}-${index}`} className="stack-item">
                <code>{path.narrative}</code>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {answer.notes.length > 0 ? (
        <section className="workspace-panel">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Diagnostics</p>
              <h2>Operator notes</h2>
            </div>
          </div>
          <p className="muted-text">{answer.notes.join(" · ")}</p>
        </section>
      ) : null}
    </>
  );
}

function AnswerBody({ text }: { text: string }) {
  const parts = splitWithMarkers(text);

  return (
    <pre className="answer-body">
      {parts.map((part, index) =>
        part.kind === "marker" ? (
          <a
            key={`${part.value}-${index}`}
            href={`#cit-${part.value}`}
            className="marker-chip"
            onClick={(event) => {
              event.preventDefault();
              const element = document.getElementById(`cit-${part.value}`);
              if (!element) {
                return;
              }
              element.scrollIntoView({ behavior: "smooth", block: "center" });
              element.classList.add("flash");
              setTimeout(() => element.classList.remove("flash"), 1200);
            }}
          >
            [{part.value}]
          </a>
        ) : (
          <span key={`${part.value}-${index}`}>{part.value}</span>
        ),
      )}
    </pre>
  );
}

function CitationCard({
  citation,
  kind,
}: {
  citation: Citation;
  kind: "public" | "private";
}) {
  return (
    <article id={`cit-${citation.marker}`} className="citation-card">
      <div className="citation-head">
        <span className="marker-label">[{citation.marker}]</span>
        <span className={`tier-pill tier-${citation.tier}`}>
          tier {citation.tier}: {tierLabel(citation.tier)}
        </span>
        <span className="stat-pill">{citation.type}</span>
        {kind === "private" ? <span className="stat-pill stat-pill-warn">private</span> : null}
      </div>

      <div className="citation-title">
        {citation.title ? <strong>{citation.title}</strong> : null}
        {citation.section_or_paragraph ? <span> · {citation.section_or_paragraph}</span> : null}
        {citation.court ? <span> · {citation.court}</span> : null}
        {!citation.court && citation.authority ? <span> · {citation.authority}</span> : null}
        {citation.date ? <span> · {citation.date}</span> : null}
      </div>

      <blockquote>{citation.excerpt}</blockquote>
      <div className="citation-provenance">
        node <code>{citation.node_id}</code> · span <code>{citation.source_span_id}</code> · file{" "}
        <code>{citation.file_id}</code>
      </div>
    </article>
  );
}

function RefusalView({ answer }: { answer: Answer }) {
  return (
    <section className="workspace-panel answer-panel refusal-panel">
      <div className="section-heading section-heading-wide">
        <div>
          <p className="section-kicker">Refusal path</p>
          <h2>No grounded answer available</h2>
        </div>
        <span className="stat-pill stat-pill-warn">insufficient evidence</span>
      </div>
      <p className="muted-text">
        The retrieval path did not surface enough authoritative material to
        support a safe answer. LexGraph kept the refusal boundary instead of
        inventing law.
      </p>
      <ul className="lane-points">
        <li>ingest more public authorities relevant to the issue</li>
        <li>upload matter-bound evidence and re-run with a matter scope</li>
        <li>anchor the question with a section, statute, or case citation</li>
      </ul>
      {answer.notes.length > 0 ? (
        <p className="muted-text">diagnostics: {answer.notes.join(" · ")}</p>
      ) : null}
    </section>
  );
}
