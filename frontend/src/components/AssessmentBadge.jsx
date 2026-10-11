const ASSESSMENTS = {
  likely_match: { label: "Likely match", tone: "green" },
  possible_match: { label: "Possible match", tone: "amber" },
  unlikely_match: { label: "Unlikely", tone: "grey" },
  insufficient_information: { label: "Not enough info", tone: "blue" },
};

export default function AssessmentBadge({ value }) {
  const { label, tone } = ASSESSMENTS[value] ?? { label: value, tone: "grey" };
  return <span className={`badge badge-${tone}`}>{label}</span>;
}
