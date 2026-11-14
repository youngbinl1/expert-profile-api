"""Parsing of career text copied from a profile database (4-line blocks) and current-role selection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:  # pycountry is only used to normalise location -> country name
    import pycountry
except Exception:  # pragma: no cover
    pycountry = None

# "Company (Mar 2021 - Now, 5 years)"  /  "Company (Jun 2016 - Feb 2021, 5 years)"
COMPANY_LINE_RE = re.compile(
    r"^(?P<company>.+?)\s*\(\s*(?P<start>[A-Za-z]+\.?\s+\d{4})\s*-\s*"
    r"(?P<end>Now|[A-Za-z]+\.?\s+\d{4})\s*,\s*(?P<years>\d+)\s*years?\s*\)\s*$",
    re.IGNORECASE,
)

US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
AU_STATES = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"}
KNOWN_REGIONS = {
    "san francisco bay area": "United States",
    "bay area": "United States",
    "silicon valley": "United States",
    "greater new york city area": "United States",
    "greater boston area": "United States",
    "london area": "United Kingdom",
    "unknown": "Unknown",
    "unknown location": "Unknown",
}
ALIASES = {
    "usa": "United States", "us": "United States", "uk": "United Kingdom", "uae": "United Arab Emirates",
    "korea": "South Korea", "hong kong": "Hong Kong",
}


@dataclass
class Entry:
    title: str
    company: str
    start: str
    end: str
    location: str
    note: str
    is_current: bool


@dataclass
class PastLine:
    text: str
    still_current: bool


@dataclass
class CareerSummary:
    current_line: str = ""
    matches_target: bool = False
    past_lines: list[PastLine] = field(default_factory=list)
    recognized: int = 0
    unresolved_locations: list[str] = field(default_factory=list)


def parse_career(raw: str) -> list[Entry]:
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    idx = [i for i, ln in enumerate(lines) if COMPANY_LINE_RE.match(ln)]
    entries: list[Entry] = []
    for pos, i in enumerate(idx):
        m = COMPANY_LINE_RE.match(lines[i])
        nxt = idx[pos + 1] - 1 if pos + 1 < len(idx) else len(lines)
        entries.append(Entry(
            title=lines[i - 1] if i - 1 >= 0 else "",
            company=m.group("company").strip(),
            start=m.group("start").strip(),
            end=m.group("end").strip(),
            location=lines[i + 1] if i + 1 < len(lines) else "",
            note=" ".join(lines[i + 2:nxt]).strip(),
            is_current=m.group("end").strip().lower() == "now",
        ))
    return entries


def location_to_country(location: str, unresolved: list[str]) -> str:
    if not location:
        return ""
    key = location.strip().lower()
    if key in KNOWN_REGIONS:
        return KNOWN_REGIONS[key]
    last = location.split(",")[-1].strip()
    up, low = last.upper(), last.lower()
    if up in US_STATES:
        return "United States"
    if up in AU_STATES:
        return "Australia"
    if low in ALIASES:
        return ALIASES[low]
    if pycountry is not None:
        try:
            return pycountry.countries.search_fuzzy(last)[0].name
        except Exception:
            pass
    unresolved.append(location)
    return location


def entry_to_line(e: Entry, unresolved: list[str]) -> str:
    country = location_to_country(e.location, unresolved)
    return f"{e.title}, {e.company} ({e.start} - {e.end})" + (f", {country}" if country else "")


def summarize(entries: list[Entry], target: str) -> CareerSummary:
    """Pick the 'current' line.

    * any current ('Now') entry at the target company -> Current (matches_target=True)
    * else the first current entry -> shown as the clearance/current line (matches_target=False)
    * no current job at all -> fixed 'Freelancer, Self-employed,' text
    """
    out = CareerSummary(recognized=len(entries))
    if not entries:
        return out
    t = target.lower()
    current = [e for e in entries if e.is_current]
    chosen = next((e for e in current if t in e.company.lower()), None)
    if chosen is not None:
        out.matches_target = True
    elif current:
        chosen = current[0]
    if chosen is not None:
        out.current_line = entry_to_line(chosen, out.unresolved_locations)
        rest = [e for e in entries if e is not chosen]
    else:
        out.current_line = "Freelancer, Self-employed,"
        rest = entries
    seen: set[str] = set()
    for e in rest:  # drop byte-identical duplicate lines
        text = entry_to_line(e, out.unresolved_locations)
        if text not in seen:
            seen.add(text)
            out.past_lines.append(PastLine(text, e.is_current))
    return out


EXPERT_PREFIX_RE = re.compile(r"^ex[-\s]?", re.IGNORECASE)


def normalize_expert_code(code: str) -> str:
    core = EXPERT_PREFIX_RE.sub("", code.strip()).strip()
    return f"EX-{core}" if core else "EX-"


VQ_MARKER_RE = re.compile(r"^\s*(?:Q)?\d+[\.\)]\s*", re.IGNORECASE)


def parse_vqs(raw: str) -> list[str]:
    if not raw.strip():
        return []
    lines = raw.split("\n")
    marks = [i for i, ln in enumerate(lines) if VQ_MARKER_RE.match(ln)]
    if not marks:
        text = " ".join(ln.strip() for ln in lines if ln.strip())
        return [text] if text else []
    qs = []
    for pos, i in enumerate(marks):
        end = marks[pos + 1] if pos + 1 < len(marks) else len(lines)
        chunk = list(lines[i:end])
        chunk[0] = VQ_MARKER_RE.sub("", chunk[0])
        q = " ".join(ln.strip() for ln in chunk if ln.strip())
        if q:
            qs.append(q)
    return qs
