"use client";

import { formatElapsed, summariseAnswer } from "@/lib/format";
import type { TraceEvent } from "@/lib/types";

type TraceTimelineProps = {
  events: TraceEvent[];
  streaming: boolean;
  startedAt: number | null;
};

export function TraceTimeline({ events, streaming, startedAt }: TraceTimelineProps) {
  if (events.length === 0 && !streaming) {
    return null;
  }

  const origin = startedAt ?? (events[0]?.ts ? events[0].ts * 1000 : Date.now());

  return (
    <section className="workspace-panel trace-panel">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Live execution</p>
          <h2>Agent trace</h2>
        </div>
        <div className="trace-status">
          {streaming ? (
            <span className="live-pill">
              <span className="spinner" />
              streaming
            </span>
          ) : (
            <span className="stat-pill">{events.length} events</span>
          )}
        </div>
      </div>

      <ol className="trace-list">
        {events.map((event, index) => (
          <TraceRow
            key={`${event.stage}-${event.ts}-${index}`}
            event={event}
            elapsedMs={Math.max(0, event.ts * 1000 - origin)}
          />
        ))}
      </ol>
    </section>
  );
}

function TraceRow({ event, elapsedMs }: { event: TraceEvent; elapsedMs: number }) {
  const hasDetails =
    (event.details && Object.keys(event.details).length > 0) || event.answer || event.error;

  return (
    <li className={`trace-row-item trace-${event.status}`}>
      <span className="trace-dot" />
      <div className="trace-row-main">
        <div className="trace-row-meta">
          <span className="trace-stage">{event.stage}</span>
          {event.worker ? <span className="trace-worker">{event.worker}</span> : null}
          <span className="trace-elapsed">+{formatElapsed(elapsedMs)}</span>
        </div>
        {event.message ? <p className="trace-message">{event.message}</p> : null}
        {hasDetails ? (
          <details className="trace-details">
            <summary>details</summary>
            <pre>
              {JSON.stringify(
                event.answer
                  ? { status: event.status, answer_summary: summariseAnswer(event.answer) }
                  : event.error
                    ? { status: event.status, error: event.error }
                    : event.details,
                null,
                2,
              )}
            </pre>
          </details>
        ) : null}
      </div>
    </li>
  );
}
