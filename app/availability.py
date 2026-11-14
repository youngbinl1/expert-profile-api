"""Interview availability -> Korea Standard Time.

The LLM only *understands* the free-form text (dates, time zone names). The actual time arithmetic,
including daylight-saving rules, is done with the IANA time zone database via zoneinfo, so results
are always correct for the given date.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.llm import LLM

log = logging.getLogger("profile-api")
DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _zone(name: str | None):
    try:
        return ZoneInfo(name) if name else None
    except Exception:
        return None


def format_slot(year: int, month: int, day: int, start: str, end: str, tz_name: str | None) -> str:
    """Convert one slot to 'MM/DD (Day) HH:MM - HH:MM KST'. No/invalid zone => already KST."""
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    kst = ZoneInfo("Asia/Seoul")
    tz = _zone(tz_name) or kst
    s = datetime(year, month, day, sh, sm, tzinfo=tz)
    e = datetime(year, month, day, eh, em, tzinfo=tz)
    if e <= s:
        e += timedelta(days=1)
    s, e = s.astimezone(kst), e.astimezone(kst)
    return f"{s:%m/%d} ({DAY_ABBR[s.weekday()]}) {s:%H:%M} - {e:%H:%M} KST"


_PROMPT = """Below is interview availability written by an expert in free form.
Today is {today} ({weekday}). Resolve relative dates ("tomorrow", "next Tuesday") from today.
Recognise the time zone however it is written (city, country, abbreviation such as PST/IST) and answer
with its exact IANA key (e.g. "America/New_York", "Asia/Kolkata", "Europe/Berlin"). Do not compute
offsets yourself. Use null when there is no time zone hint.
Reply with a pure JSON array only (no code fences, no prose). Each item:
{{"year": int, "month": int, "day": int, "start_time": "HH:MM", "end_time": "HH:MM",
  "iana_timezone": string or null}}

Text:
{raw}"""

_ISO_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})(?:\s+([A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?))?"
)


def _mock_slots(raw: str) -> list[dict]:
    """Deterministic parser for 'YYYY-MM-DD HH:MM-HH:MM Region/City' used when no LLM is available."""
    return [
        {"year": int(y), "month": int(mo), "day": int(d), "start_time": s, "end_time": e, "iana_timezone": tz}
        for y, mo, d, s, e, tz in _ISO_RE.findall(raw)
    ]


def _llm_slots(llm: LLM, raw: str, today: datetime) -> list[dict] | None:
    prompt = _PROMPT.format(today=today.strftime("%Y-%m-%d"), weekday=DAY_ABBR[today.weekday()], raw=raw)
    for _ in range(2):
        try:
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", llm.complete(prompt, 800).strip())
            slots = json.loads(text)
            if isinstance(slots, list) and slots:
                return slots
        except Exception as exc:
            log.warning("availability parsing failed: %s", exc)
    return None


def to_kst(raw: str, llm: LLM, today: datetime | None = None) -> str:
    """Return the converted slots joined by ', ', or '' if nothing could be parsed."""
    raw = raw.strip()
    if not raw:
        return ""
    today = today or datetime.now()
    slots = _llm_slots(llm, raw, today) if llm.enabled else None
    if slots is None:
        slots = _mock_slots(raw)
    if not slots:
        return ""
    default_tz = next((s.get("iana_timezone") for s in slots if s.get("iana_timezone")), None)
    out = []
    for s in slots:
        try:
            out.append(format_slot(
                int(s.get("year") or today.year), int(s["month"]), int(s["day"]),
                s["start_time"], s["end_time"], s.get("iana_timezone") or default_tz,
            ))
        except Exception:
            continue  # skip a bad slot, keep the others
    return ", ".join(out)
