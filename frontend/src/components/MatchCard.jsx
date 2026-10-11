import { useState } from "react";
import AssessmentBadge from "./AssessmentBadge.jsx";
import ScoreBreakdown from "./ScoreBreakdown.jsx";
import EvidenceList from "./EvidenceList.jsx";
import FeedbackButtons from "./FeedbackButtons.jsx";
import { photoSrc, USE_MOCKS } from "../api.js";
import { categoryLabel, formatDateTime, orDash } from "../format.js";

export default function MatchCard({ candidate }) {
  const [status, setStatus] = useState(candidate.feedback_status);
  const report = candidate.candidate;
  const src = photoSrc(report.photo_url);

  return (
    <article className="card match-card">
      <div className="match-top">
        <AssessmentBadge value={candidate.assessment} />
        <span className="small muted">
          Report #{candidate.candidate_report_id}
        </span>
      </div>

      <ScoreBreakdown
        score={candidate.ranking_score}
        breakdown={candidate.score_breakdown}
      />

      <div className="section-label">Their report</div>
      <div className="candidate-box">
        <p>{report.description}</p>
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
        {src && <img className="photo" src={src} alt="Photo of the found item" />}
        {!src && report.has_photo && (
          <span className="photo-note">
            📷 Photo attached —{" "}
            {USE_MOCKS ? "shown once the backend is connected" : "could not be loaded"}
          </span>
        )}
      </div>

      {candidate.matching_evidence?.length > 0 && (
        <>
          <div className="section-label">Why it may match</div>
          <EvidenceList items={candidate.matching_evidence} tone="good" />
        </>
      )}

      {candidate.conflicting_evidence?.length > 0 && (
        <>
          <div className="section-label">Why it may not</div>
          <EvidenceList items={candidate.conflicting_evidence} tone="bad" />
        </>
      )}

      {candidate.missing_information?.length > 0 && (
        <>
          <div className="section-label">Still unknown</div>
          <ul className="unknown-list">
            {candidate.missing_information.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {candidate.next_step && (
        <div className="next-step">
          <div className="section-label">What to do next</div>
          <p>{candidate.next_step}</p>
        </div>
      )}

      <FeedbackButtons
        matchId={candidate.match_id}
        status={status}
        onUpdated={setStatus}
      />
    </article>
  );
}
