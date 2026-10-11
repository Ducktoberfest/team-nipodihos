import { useState } from "react";
import { createReport } from "../api.js";
import { CATEGORIES, categoryLabel, localInputToIso, maxLocalInput } from "../format.js";

const EMPTY = {
  description: "",
  category: "",
  color: "",
  location: "",
  occurredAt: "",
  privateDetails: "",
  contact: "",
};

function validate(form) {
  const errors = {};
  const description = form.description.trim();

  if (description.length < 10) {
    errors.description = "Please describe the item in at least 10 characters.";
  } else if (description.length > 2000) {
    errors.description = "Please keep the description under 2000 characters.";
  }
  if (form.color.trim().length > 50) {
    errors.color = "Color must be 50 characters or fewer.";
  }
  if (form.location.trim().length > 200) {
    errors.location = "Location must be 200 characters or fewer.";
  }
  if (form.privateDetails.trim().length > 500) {
    errors.privateDetails = "Private details must be 500 characters or fewer.";
  }
  if (form.contact.trim().length > 200) {
    errors.contact = "Contact must be 200 characters or fewer.";
  }
  if (form.occurredAt) {
    const when = new Date(form.occurredAt);
    if (Number.isNaN(when.getTime())) {
      errors.occurredAt = "That date does not look valid.";
    } else if (when.getTime() > Date.now() + 60000) {
      errors.occurredAt = "The date cannot be in the future.";
    }
  }
  return errors;
}

const orNull = (value) => {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

export default function ReportForm({ initialType = "lost", onCreated }) {
  const [type, setType] = useState(initialType);
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  const set = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const report = await createReport({
        type,
        description: form.description.trim(),
        category: orNull(form.category),
        color: orNull(form.color),
        location: orNull(form.location),
        occurred_at: localInputToIso(form.occurredAt),
        private_details: orNull(form.privateDetails),
        contact: orNull(form.contact),
      });
      onCreated(report);
    } catch (err) {
      setServerError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const count = form.description.trim().length;

  return (
    <div>
      <div className="page-head">
        <h1>Report an item</h1>
        <p>
          Describe it the way you would to a friend. The AI handles the
          wording — you do not need to guess the "right" words.
        </p>
      </div>

      <form className="card" onSubmit={handleSubmit} noValidate>
        <div className="field">
          <span className="label">What happened?</span>
          <div className="btn-group">
            <button
              type="button"
              className={`chip ${type === "lost" ? "active" : ""}`}
              onClick={() => setType("lost")}
            >
              I lost it
            </button>
            <button
              type="button"
              className={`chip ${type === "found" ? "active" : ""}`}
              onClick={() => setType("found")}
            >
              I found it
            </button>
          </div>
        </div>

        <label className={`field ${errors.description ? "invalid" : ""}`}>
          <span className="label">Description *</span>
          <span className="hint">
            What is it, where was it, what stands out about it?
          </span>
          <textarea
            value={form.description}
            onChange={set("description")}
            placeholder="I lost my dark blue backpack near the university library. It had a laptop and a small keychain inside."
            maxLength={2000}
          />
          <span className="counter">{count} / 2000</span>
          {errors.description && (
            <span className="field-error">{errors.description}</span>
          )}
        </label>

        <div className="field-grid">
          <label className="field">
            <span className="label">Category</span>
            <select value={form.category} onChange={set("category")}>
              <option value="">Not sure</option>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {categoryLabel(value)}
                </option>
              ))}
            </select>
          </label>

          <label className={`field ${errors.color ? "invalid" : ""}`}>
            <span className="label">Color</span>
            <input
              value={form.color}
              onChange={set("color")}
              placeholder="dark blue"
              maxLength={50}
            />
            {errors.color && <span className="field-error">{errors.color}</span>}
          </label>

          <label className={`field ${errors.location ? "invalid" : ""}`}>
            <span className="label">Location</span>
            <input
              value={form.location}
              onChange={set("location")}
              placeholder="Main Library"
              maxLength={200}
            />
            {errors.location && (
              <span className="field-error">{errors.location}</span>
            )}
          </label>

          <label className={`field ${errors.occurredAt ? "invalid" : ""}`}>
            <span className="label">When</span>
            <input
              type="datetime-local"
              value={form.occurredAt}
              onChange={set("occurredAt")}
              max={maxLocalInput()}
            />
            {errors.occurredAt && (
              <span className="field-error">{errors.occurredAt}</span>
            )}
          </label>
        </div>

        <label className={`field ${errors.privateDetails ? "invalid" : ""}`}>
          <span className="label">Private details</span>
          <span className="hint">
            Only used by the AI to verify ownership. Never shown to anyone.
          </span>
          <textarea
            value={form.privateDetails}
            onChange={set("privateDetails")}
            placeholder="Keychain is a small silver Eiffel Tower."
            maxLength={500}
            style={{ minHeight: 70 }}
          />
          {errors.privateDetails && (
            <span className="field-error">{errors.privateDetails}</span>
          )}
        </label>

        <label className={`field ${errors.contact ? "invalid" : ""}`}>
          <span className="label">Contact</span>
          <span className="hint">
            So the lost-and-found desk can reach you. Never shown publicly.
          </span>
          <input
            value={form.contact}
            onChange={set("contact")}
            placeholder="student@example.edu"
            maxLength={200}
          />
          {errors.contact && (
            <span className="field-error">{errors.contact}</span>
          )}
        </label>

        {serverError && (
          <div className="banner banner-error" style={{ marginBottom: 14 }}>
            {serverError}
          </div>
        )}

        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? "Submitting…" : "Submit and find matches"}
        </button>
      </form>
    </div>
  );
}
