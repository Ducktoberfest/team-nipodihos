import { useEffect, useRef, useState } from "react";
import MatchCard from "./MatchCard.jsx";
import { findMatches, getMatches, getReport } from "../api.js";
import { categoryLabel, formatDateTime, orDash } from "../format.js";

export default function MatchesView({ reportId, autoRun = false, onBack }) {
  const [report, setReport] = useState(null);
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState(null);
  // Remembers which report already auto-ran, so React's dev double-effects
  // and re-renders never trigger a second (paid) AI call.
  const autoRanFor = useRef(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setRun(null);

    Promise.all([getReport(reportId), getMatches(reportId)])
      .then(([loadedReport, loadedRun]) => {
        if (!active) return;
        setReport(loadedReport);
        setRun(loadedRun?.generated_at ? loadedRun : null);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reportId]);

  useEffect(() => {
    if (autoRun && !loading && report && !run && autoRanFor.current !== reportId) {
      autoRanFor.current = reportId;
      runMatching();
    }
    // runMatching only depends on reportId, which is already listed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, loading, report, run, reportId]);

  async function runMatching() {
    setMatching(true);
    setError(null);
    try {
      setRun(await findMatches(reportId));
    } catch (err) {
      setError(err.message);
    } finally {
      setMatching(false);
    }
  }

  if (loading) {
    return (
      <div className="state">
        <div className="spinner" />
        Loading report…
      </div>
    );
  }

  if (error && !report) {
    return (
      <div>
        <button className="back-link" onClick={onBack}>
          ← Back to reports
        </button>
        <div className="banner banner-error">{error}</div>
      </div>
    );
  }

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        ← Back to reports
      </button>

      <div className="page-head">
        <h1>Possible matches</h1>
        <p>
          Candidates are {report.type === "lost" ? "found" : "lost"} reports,
          ranked by how well their details line up with yours.
        </p>
      </div>

      <section className="card" style={{ marginBottom: 18 }}>
        <div className="card-top" style={{ marginBottom: 8 }}>
          <span className={`badge badge-${report.type}`}>{report.type}</span>
          <span className="small muted">Your report #{report.id}</span>
        </div>
        <p className="desc">{report.description}</p>
        <div className="meta">
          <span>
            <b>Category</b> {orDash(categoryLabel(report.category))}
          </span>
          <span>
            <b>Color</b> {orDash(report.color)}
          </span>
          <span>
            <b>Location</b> {orDash(report.location)}
          </span>
          <span>
            <b>When</b> {orDash(formatDateTime(report.occurred_at))}
          </span>
        </div>
        <button className="btn" onClick={runMatching} disabled={matching}>
          {matching
            ? "Matching…"
            : run
              ? "Run matching again"
              : "Find matches"}
        </button>
        {run?.generated_at && !matching && (
          <p className="small muted" style={{ margin: "10px 0 0" }}>
            Last run {formatDateTime(run.generated_at)} ·{" "}
            {run.candidates_considered} report
            {run.candidates_considered === 1 ? "" : "s"} considered
          </p>
        )}
      </section>

      {matching && (
        <div className="state">
          <div className="spinner" />
          AI is comparing reports… (this takes a few seconds)
        </div>
      )}

      {error && report && !matching && (
        <div className="banner banner-error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!matching && run?.degraded && (
        <div className="banner banner-warning" style={{ marginBottom: 16 }}>
          <strong>AI unavailable.</strong>{" "}
          {run.degraded_reason ??
            "Showing rule-based results only."}{" "}
          Colors and free-text features were not compared, so suggestions are
          less reliable than usual.
        </div>
      )}

      {!matching && !run && !error && (
        <div className="state">
          No matching has been run for this report yet. Press{" "}
          <strong>Find matches</strong> to start.
        </div>
      )}

      {!matching && run && run.candidates.length === 0 && (
        <div className="state">
          No similar reports yet. We'll keep your report open.
        </div>
      )}

      {!matching && run && run.candidates.length > 0 && (
        <div className="stack">
          {run.candidates.map((candidate) => (
            <MatchCard key={candidate.match_id} candidate={candidate} />
          ))}
        </div>
      )}

      {!matching && run && run.candidates.length > 0 && (
        <p className="small muted" style={{ marginTop: 18 }}>
          Suggestions are not proof. Always verify before handing over an item.
        </p>
      )}
    </div>
  );
}
