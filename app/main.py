"""Expert Profile API - FastAPI service that turns raw career text + screening questions into a
formatted email-ready profile."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from app.availability import to_kst
from app.career import normalize_expert_code, parse_career, parse_vqs, summarize
from app.config import get_settings
from app.llm import LLM, generate_comment
from app.models import ProfileRequest, ProfileResponse
from app.render import render_email
from app.sample_data import samples
from app.storage import get_store, new_id


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to filter in CloudWatch Logs Insights."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "logger": record.name, "message": record.getMessage()})


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler], force=True)
log = logging.getLogger("profile-api")

app = FastAPI(title="Expert Profile API", version="1.0.0")
STATIC_DIR = Path(__file__).parent / "static"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    s = get_settings()
    if s.auth_disabled:
        return
    if not s.app_api_key:
        raise HTTPException(503, "Server is not configured: APP_API_KEY is missing")
    if not x_api_key or not secrets.compare_digest(x_api_key, s.app_api_key):
        raise HTTPException(401, "Invalid or missing API key")


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "llm": bool(s.anthropic_api_key), "storage": get_store().kind}


@app.get("/api/sample")
def sample() -> list[dict]:
    """Synthetic demo inputs (no real data)."""
    return samples()


@app.post("/api/profile", response_model=ProfileResponse, dependencies=[Depends(require_api_key)])
def create_profile(req: ProfileRequest) -> ProfileResponse:
    s = get_settings()
    llm = LLM(s.anthropic_api_key, s.llm_model)
    warnings: list[str] = []

    entries = parse_career(req.career_text)
    career = summarize(entries, req.target_company)
    if not entries:
        warnings.append("Career format was not recognised; the career lines were left empty.")
    if career.unresolved_locations:
        warnings.append("Could not map to a country (kept as written): " + " / ".join(career.unresolved_locations))

    vqs = parse_vqs(req.vq_text)
    availability = to_kst(req.availability_text, llm, datetime.now())
    if req.availability_text.strip() and not availability:
        warnings.append("Availability could not be converted; left blank.")

    comment, warn = generate_comment(
        llm, req.target_company, career.current_line, [p.text for p in career.past_lines], vqs)
    if warn:
        warnings.append(warn)

    code = normalize_expert_code(req.expert_code)
    html = render_email(req, code, career, comment, availability, vqs)
    pid = new_id()
    try:
        get_store().save({"id": pid, "style": req.style, "target_company": req.target_company,
                          "expert_code": code, "comment": comment, "html": html})
    except Exception as exc:  # never fail the request because history could not be saved
        log.error("history save failed: %s", exc)
        warnings.append("History could not be saved.")

    log.info("profile created id=%s style=%s entries=%d llm=%s", pid, req.style, len(entries), llm.enabled)
    return ProfileResponse(id=pid, html=html, comment=comment, availability_kst=availability,
                           career_entries=len(entries), warnings=warnings)


@app.get("/api/profiles", dependencies=[Depends(require_api_key)])
def recent_profiles(limit: int = 10) -> list[dict]:
    items = get_store().recent(max(1, min(limit, 50)))
    return [{k: v for k, v in it.items() if k != "html"} for it in items]


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
