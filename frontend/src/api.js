import mockReports from "./mocks/mock_reports.json";
import mockMatches from "./mocks/mock_matches.json";
import mockMatchesDegraded from "./mocks/mock_matches_degraded.json";

// Real backend by default. For mock data: VITE_USE_MOCKS=true npm run dev
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";
export const MOCK_DEGRADED = import.meta.env.VITE_MOCK_DEGRADED === "true";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new Error(
      `Cannot reach the API at ${BASE}. Is the backend running?`
    );
  }
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(body?.error?.message ?? `Request failed (${res.status})`);
  }
  return body;
}

const sessionReports = [];
const sessionMatchRuns = {};
const sessionFeedback = {};
let nextMockId = 1000;

function mockPool() {
  return [...sessionReports, ...mockReports.items];
}

function applyStoredFeedback(run) {
  return {
    ...run,
    candidates: run.candidates.map((c) => ({
      ...c,
      feedback_status: sessionFeedback[c.match_id] ?? c.feedback_status,
    })),
  };
}

export async function listReports(type) {
  if (USE_MOCKS) {
    await wait(700);
    const items = mockPool().filter((r) => !type || r.type === type);
    return { items, total: items.length };
  }
  const query = type ? `?type=${encodeURIComponent(type)}` : "";
  return request(`/reports${query}`);
}

export async function getReport(id) {
  if (USE_MOCKS) {
    await wait(400);
    const report = mockPool().find((r) => String(r.id) === String(id));
    if (!report) throw new Error("Report not found");
    return report;
  }
  return request(`/reports/${id}`);
}

export async function createReport(data) {
  if (USE_MOCKS) {
    await wait(900);
    const report = {
      id: ++nextMockId,
      type: data.type,
      description: data.description,
      category: data.category ?? null,
      color: data.color ?? null,
      location: data.location ?? null,
      occurred_at: data.occurred_at ?? null,
      has_photo: false,
      photo_url: null,
      has_private_details: Boolean(data.private_details),
      status: "open",
      created_at: new Date().toISOString(),
      ai_attributes: { extraction_status: "pending" },
    };
    sessionReports.unshift(report);
    return report;
  }
  return request("/reports", { method: "POST", body: JSON.stringify(data) });
}

export async function findMatches(reportId, limit = 5) {
  if (USE_MOCKS) {
    await wait(2500);
    const source = MOCK_DEGRADED ? mockMatchesDegraded : mockMatches;
    const run = {
      ...source,
      report_id: Number(reportId),
      generated_at: new Date().toISOString(),
      candidates: source.candidates
        .filter((c) => String(c.candidate_report_id) !== String(reportId))
        .slice(0, limit),
    };
    sessionMatchRuns[reportId] = run;
    return applyStoredFeedback(run);
  }
  return request(`/reports/${reportId}/matches`, {
    method: "POST",
    body: JSON.stringify({ limit }),
  });
}

export async function getMatches(reportId) {
  if (USE_MOCKS) {
    await wait(300);
    const run = sessionMatchRuns[reportId];
    if (!run) {
      return {
        report_id: Number(reportId),
        generated_at: null,
        degraded: false,
        degraded_reason: null,
        candidates_considered: 0,
        candidates: [],
      };
    }
    return applyStoredFeedback(run);
  }
  return request(`/reports/${reportId}/matches`);
}

export async function sendFeedback(matchId, status, note) {
  if (USE_MOCKS) {
    await wait(600);
    sessionFeedback[matchId] = status;
    return {
      match_id: Number(matchId),
      feedback_status: status,
      updated_at: new Date().toISOString(),
    };
  }
  return request(`/matches/${matchId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ status, note: note || null }),
  });
}

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

export async function uploadPhoto(reportId, file) {
  if (USE_MOCKS) {
    await wait(700);
    const report = mockPool().find((r) => String(r.id) === String(reportId));
    if (report) {
      report.has_photo = true;
      report.photo_url = `/reports/${reportId}/photo`;
    }
    return report;
  }

  const form = new FormData();
  form.append("file", file);

  let res;
  try {
    // No Content-Type header: the browser must set the multipart boundary itself.
    res = await fetch(`${BASE}/reports/${reportId}/photo`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new Error(`Cannot reach the API at ${BASE}. Is the backend running?`);
  }

  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(body?.error?.message ?? `Photo upload failed (${res.status})`);
  }
  return body;
}

export function photoSrc(photoUrl) {
  if (!photoUrl) return null;
  return USE_MOCKS ? null : BASE + photoUrl;
}
