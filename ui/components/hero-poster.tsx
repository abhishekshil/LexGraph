import { ARCHITECTURE_LANES, DELIVERY_METRICS } from "@/lib/content";

export function HeroPoster() {
  return (
    <section className="hero-poster">
      <div className="hero-orbit hero-orbit-left" />
      <div className="hero-orbit hero-orbit-right" />
      <div className="hero-grid">
        <div className="hero-copy">
          <p className="eyebrow">LexGraph / Research Workspace</p>
          <h1>Graph memory for Indian legal research.</h1>
          <p className="hero-summary">
            Version 1 is a research-first operator surface: ingest matter files,
            run graph-first queries, inspect evidence traces, and keep the
            product boundary honest while the drafting engine stays future scope.
          </p>
          <div className="hero-actions">
            <a className="button-link button-link-primary" href="#research-console">
              Open workspace
            </a>
            <a className="button-link button-link-secondary" href="#runtime-panel">
              Inspect runtime
            </a>
          </div>
        </div>

        <div className="hero-map" aria-label="Architecture alignment">
          <div className="hero-map-head">
            <span className="eyebrow">Direction check</span>
            <p>
              The shared platform and research engine are real. Drafting remains
              deliberately deferred.
            </p>
          </div>
          <div className="hero-map-flow">
            {ARCHITECTURE_LANES.map((lane) => (
              <article key={lane.title} className={`lane lane-${lane.status}`}>
                <div className="lane-status">{lane.status}</div>
                <h2>{lane.title}</h2>
                <p>{lane.summary}</p>
                <ul className="lane-points">
                  {lane.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </div>

      <div className="hero-metrics">
        {DELIVERY_METRICS.map((metric) => (
          <div key={metric.label} className="metric">
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
