import { useEffect, useState } from "react";
import { listReports } from "../api.js";
import { categoryLabel, formatDateTime, orDash } from "../format.js";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "lost", label: "Lost" },
  { value: "found", label: "Found" },
];

function ReportCard({ report, onOpenMatches }) {
  return (
    <article className="card report-card">
      <div className="card-top">
        <span className={`badge badge-${report.type}`}>{report.type}</span>
        {report.status === "matched" && (
          <span className="badge badge-green">matched</span>
        )}
        {report.has_photo && <span className="small muted">📷 photo</span>}
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

      <button
        className="btn secondary small"
        onClick={() => onOpenMatches(report.id)}
      >
        Find matches
      </button>
    </article>
  );
}

export default function ReportList({ onOpenMatches }) {
  const [filter, setFilter] = useState("all");
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    listReports(filter === "all" ? undefined : filter)
      .then((data) => {
        if (active) setReports(data.items ?? []);
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
  }, [filter, reloadKey]);

  return (
    <div>
      <div className="page-head">
        <h1>Browse reports</h1>
        <p>Lost and found items reported on campus, newest first.</p>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        {FILTERS.map((option) => (
          <button
            key={option.value}
            className={`chip ${filter === option.value ? "active" : ""}`}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="state">
          <div className="spinner" />
          Loading reports…
        </div>
      )}

      {!loading && error && (
        <div className="banner banner-error">
          {error}
          <div style={{ marginTop: 10 }}>
            <button
              className="btn secondary small"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && reports.length === 0 && (
        <div className="state">No reports yet.</div>
      )}

      {!loading && !error && reports.length > 0 && (
        <div className="stack">
          {reports.map((report) => (
            <ReportCard
              key={report.id}
              report={report}
              onOpenMatches={onOpenMatches}
            />
          ))}
        </div>
      )}
    </div>
  );
}
