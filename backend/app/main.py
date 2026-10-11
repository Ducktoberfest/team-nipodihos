"""FoundIt API. Run from the repo root: uvicorn app.main:app --reload --app-dir backend"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # before importing the AI module, which may read env at import time

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from . import ai_bridge, db  # noqa: E402
from .models import (  # noqa: E402
    FeedbackIn, FeedbackOut, MatchRequest, MatchResponse, ReportCreate, ReportList, ReportOut,
    ReportStatus, ReportType, row_to_candidate, row_to_report_out, to_utc_iso,
)

logger = logging.getLogger("foundit.api")

MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MEDIA_TYPES = {ext: mime for mime, ext in PHOTO_TYPES.items()}


def get_upload_dir() -> Path:
    return Path(os.getenv("FOUNDIT_UPLOAD_DIR", str(db.BACKEND_DIR / "uploads")))


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    if not ai_bridge.AI_MODULE_AVAILABLE:
        logger.warning("foundit_ai not installed: /matches serves sample_data/mock_matches.json")
    yield


app = FastAPI(title="FoundIt API", version="0.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- errors (docs/API.md "Errors") ----------

HTTP_ERROR_CODES = {
    404: "not_found",
    405: "method_not_allowed",
    413: "file_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
}

ISSUE_NAMES = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "literal_error": "invalid_choice",
    "greater_than_equal": "too_small",
    "less_than_equal": "too_large",
    "value_error": "invalid",
}


def error_response(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": {"code": code, "message": message, "details": details or []}})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]),
                "issue": ISSUE_NAMES.get(e["type"], e["type"])} for e in errors]
    first = errors[0] if errors else {"msg": "Invalid request", "loc": ()}
    msg = first["msg"].removeprefix("Value error, ")
    field = ".".join(str(p) for p in first["loc"][1:])
    message = f"{field}: {msg}" if field else msg
    return error_response(422, "validation_error", message, details)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, HTTP_ERROR_CODES.get(exc.status_code, "http_error"),
                          str(exc.detail))


@app.exception_handler(Exception)
async def internal_error(_: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong on the server.")


def require_report(conn, report_id: int):
    row = db.get_report(conn, report_id)
    if row is None:
        raise HTTPException(404, f"Report {report_id} not found")
    return row


# ---------- health ----------

@app.get("/health")
def health():
    return {"status": "ok", "ai_available": ai_bridge.ai_available()}


# ---------- reports ----------

@app.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportCreate):
    data = body.model_dump()
    data["occurred_at"] = to_utc_iso(body.occurred_at) if body.occurred_at else None
    data["status"] = "open"
    data["created_at"] = db.utc_now_iso()
    with db.connect() as conn:
        report_id = db.insert_report(conn, data)
    # Extraction runs outside the insert transaction so a slow model call doesn't hold a DB lock.
    with db.connect() as conn:
        row = db.get_report(conn, report_id)
    attributes_json = ai_bridge.extract(row)
    with db.connect() as conn:
        if attributes_json is not None:
            db.set_ai_attributes(conn, report_id, attributes_json)
        return row_to_report_out(db.get_report(conn, report_id))


@app.get("/reports", response_model=ReportList)
def list_reports(
    type_: ReportType | None = Query(None, alias="type"),
    status: ReportStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    with db.connect() as conn:
        rows, total = db.list_reports(conn, type_, status, limit)
    return ReportList(items=[row_to_report_out(r) for r in rows], total=total)


@app.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int):
    with db.connect() as conn:
        return row_to_report_out(require_report(conn, report_id))


# ---------- photos ----------

def sniff_image_type(head: bytes) -> str | None:
    """Check the file's real signature instead of trusting the client's Content-Type."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.post("/reports/{report_id}/photo", response_model=ReportOut)
async def upload_photo(report_id: int, file: UploadFile = File(...)):
    with db.connect() as conn:
        old_path = require_report(conn, report_id)["photo_path"]

    content = await file.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo must be 5 MB or smaller")
    mime = sniff_image_type(content[:12])
    if file.content_type not in PHOTO_TYPES or mime is None:
        raise HTTPException(415, "Photo must be a JPEG, PNG or WebP image")

    # Server-generated name only: the uploaded filename is never used (path traversal).
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{PHOTO_TYPES[mime]}"
    (upload_dir / filename).write_bytes(content)

    with db.connect() as conn:
        db.set_photo_path(conn, report_id, filename)
        row = db.get_report(conn, report_id)
    if old_path:
        (upload_dir / old_path).unlink(missing_ok=True)
    return row_to_report_out(row)


@app.get("/reports/{report_id}/photo")
def get_photo(report_id: int):
    with db.connect() as conn:
        photo_path = require_report(conn, report_id)["photo_path"]
    path = get_upload_dir() / photo_path if photo_path else None
    if path is None or not path.is_file():
        raise HTTPException(404, f"Report {report_id} has no photo")
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"))


# ---------- matches ----------

def build_match_response(conn, report_id: int) -> MatchResponse:
    """Rebuild the API response from the saved run + current matches rows + current reports."""
    run = db.get_match_run(conn, report_id)
    if run is None:
        return MatchResponse(report_id=report_id, generated_at=None, degraded=False,
                             degraded_reason=None, candidates_considered=0, candidates=[])
    match_rows = db.get_matches_for_report(conn, report_id)
    candidates = []
    for cand in run.get("candidates", []):
        cand_id = cand["candidate_report_id"]
        cand_row = db.get_report(conn, cand_id)
        match_row = match_rows.get(cand_id)
        if cand_row is None or match_row is None:
            continue
        candidates.append({
            **cand,
            "match_id": match_row["id"],
            "feedback_status": match_row["feedback_status"],
            # Always built from our DB, never from the AI output: no contact/private details.
            "candidate": row_to_candidate(cand_row).model_dump(),
        })
    return MatchResponse.model_validate({**run, "report_id": report_id, "candidates": candidates})


@app.post("/reports/{report_id}/matches", response_model=MatchResponse)
def run_matches(report_id: int, body: MatchRequest | None = None):
    limit = (body or MatchRequest()).limit
    with db.connect() as conn:
        query = require_report(conn, report_id)
        pool = db.list_other_reports(conn, report_id)

    run = ai_bridge.run_matching(query, pool, limit)  # may take seconds; no DB lock held

    for cand in run.get("candidates", []):
        cand.pop("match_id", None)
        cand.pop("feedback_status", None)
        cand.pop("candidate", None)
    with db.connect() as conn:
        for cand in run.get("candidates", []):
            db.upsert_match(conn, report_id, cand["candidate_report_id"])
        db.save_match_run(conn, report_id, run)
        return build_match_response(conn, report_id)


@app.get("/reports/{report_id}/matches", response_model=MatchResponse)
def get_matches(report_id: int):
    with db.connect() as conn:
        require_report(conn, report_id)
        return build_match_response(conn, report_id)


# ---------- feedback ----------

@app.post("/matches/{match_id}/feedback", response_model=FeedbackOut)
def match_feedback(match_id: int, body: FeedbackIn):
    with db.connect() as conn:
        match = db.get_match(conn, match_id)
        if match is None:
            raise HTTPException(404, f"Match {match_id} not found")
        updated_at = db.update_match_feedback(conn, match_id, body.status, body.note)
        if body.status == "confirmed":
            db.set_report_status(conn, [match["report_id"], match["candidate_report_id"]], "matched")
    return FeedbackOut(match_id=match_id, feedback_status=body.status, updated_at=updated_at)
