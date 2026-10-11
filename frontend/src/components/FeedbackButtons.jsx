import { useState } from "react";
import { sendFeedback } from "../api.js";

const STATUS_LABELS = {
  confirmed: { text: "You confirmed this is your item", tone: "green" },
  rejected: { text: "You marked this as not yours", tone: "grey" },
  uncertain: { text: "You marked this as not sure", tone: "amber" },
};

export default function FeedbackButtons({ matchId, status, onUpdated }) {
  const [sending, setSending] = useState(null);
  const [error, setError] = useState(null);

  if (status && status !== "pending") {
    const label = STATUS_LABELS[status] ?? { text: status, tone: "grey" };
    return (
      <div className="feedback">
        <span className={`badge badge-${label.tone}`}>{label.text}</span>
      </div>
    );
  }

  async function submit(next) {
    if (
      next === "confirmed" &&
      !window.confirm(
        "Only confirm after verifying a private detail with the finder. Confirm now?"
      )
    ) {
      return;
    }
    setSending(next);
    setError(null);
    try {
      const result = await sendFeedback(matchId, next);
      onUpdated(result.feedback_status);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(null);
    }
  }

  return (
    <div className="feedback">
      <div className="btn-group">
        <button
          className="btn small"
          disabled={Boolean(sending)}
          onClick={() => submit("confirmed")}
        >
          {sending === "confirmed" ? "Saving…" : "Confirm — it's mine"}
        </button>
        <button
          className="btn secondary small"
          disabled={Boolean(sending)}
          onClick={() => submit("rejected")}
        >
          {sending === "rejected" ? "Saving…" : "Not mine"}
        </button>
        <button
          className="btn secondary small"
          disabled={Boolean(sending)}
          onClick={() => submit("uncertain")}
        >
          {sending === "uncertain" ? "Saving…" : "Not sure"}
        </button>
      </div>
      {error && (
        <p className="small" style={{ color: "var(--red)", marginTop: 8 }}>
          {error}
        </p>
      )}
    </div>
  );
}
