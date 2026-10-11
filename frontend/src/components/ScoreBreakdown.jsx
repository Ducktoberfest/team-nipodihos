import { attributeLabel } from "../format.js";

const RESULTS = {
  agree: { icon: "✓", word: "agree" },
  partial: { icon: "~", word: "partial" },
  conflict: { icon: "✗", word: "conflict" },
  unknown: { icon: "?", word: "unknown" },
};

export default function ScoreBreakdown({ score, breakdown = [] }) {
  const clamped = Math.max(0, Math.min(100, score ?? 0));

  return (
    <div className="score">
      <div className="score-head">
        <span className="section-label" style={{ margin: 0 }}>
          Ranking score
        </span>
        <span className="value">
          {clamped}
          <small> / 100</small>
        </span>
      </div>

      <div
        className="bar"
        role="img"
        aria-label={`Ranking score ${clamped} out of 100`}
      >
        <div style={{ width: `${clamped}%` }} />
      </div>

      <span className="small muted">
        Points from matching details — not a probability.
      </span>

      <ul className="breakdown">
        {breakdown.map((row) => {
          const result = RESULTS[row.result] ?? { icon: "·", word: row.result };
          return (
            <li key={row.attribute}>
              <span
                className={`icon r-${row.result}`}
                title={result.word}
                aria-hidden="true"
              >
                {result.icon}
              </span>
              <span>
                {attributeLabel(row.attribute)}{" "}
                <span className="muted small">({result.word})</span>
              </span>
              <span className="points">
                {row.points}/{row.max}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
