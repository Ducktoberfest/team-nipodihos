import { attributeLabel, PRIVATE_PLACEHOLDER } from "../format.js";

function Side({ who, value }) {
  if (value === PRIVATE_PLACEHOLDER) {
    return (
      <div className="side">
        <span className="who">{who}</span>
        <span className="lock">
          🔒 Private detail — describe it to the finder
        </span>
      </div>
    );
  }
  return (
    <div className="side">
      <span className="who">{who}</span>
      {value ?? "—"}
    </div>
  );
}

export default function EvidenceList({ items = [], tone }) {
  if (items.length === 0) return null;

  return (
    <ul className={`evidence ${tone === "good" ? "good" : "bad"}`}>
      {items.map((item, index) => (
        <li key={`${item.attribute}-${index}`}>
          <div className="attr">
            {attributeLabel(item.attribute)}
            {item.source === "rule" && " · checked by code"}
            {item.source === "photo" && " · from photo"}
          </div>
          <div className="compare">
            <Side who="Your report" value={item.this_report} />
            <Side who="Their report" value={item.candidate} />
          </div>
          <p className="note">{item.note}</p>
        </li>
      ))}
    </ul>
  );
}
