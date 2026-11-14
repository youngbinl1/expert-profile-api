"""Render the email body as HTML with inline styles (pastes cleanly into Outlook)."""
from __future__ import annotations

from html import escape

from app.career import CareerSummary
from app.models import ProfileRequest

FONT = "font-family:Calibri,'Malgun Gothic',sans-serif;"

TEXT = {
    "ko": {
        "greet": lambda r: f"안녕하세요 {r}," if r else "안녕하세요,",
        "intro": lambda client, user, target: " ".join(x for x in [client, user, target] if x) + " 프로필 송부드립니다.",
        "thanks": "감사합니다.",
    },
    "en": {
        "greet": lambda r: f"Hello {r}," if r else "Hello,",
        "intro": lambda client, user, target: "Please find the " + " ".join(x for x in [client, user, target] if x) + " profile below.",
        "thanks": "Best regards,",
    },
}


def _run(text: str, *, b=False, i=False, u=False, color=None, hl=None, size=10) -> str:
    style = f"{FONT}font-size:{size}pt;"
    style += "font-weight:bold;" if b else ""
    style += "font-style:italic;" if i else ""
    style += "text-decoration:underline;" if u else ""
    style += f"color:{color};" if color else ""
    if hl == "yellow":
        style += "background:#FFFF00;mso-highlight:yellow;"
    elif hl == "turquoise":
        style += "background:#00FFFF;mso-highlight:turquoise;"
    return f'<span style="{style}">{escape(text)}</span>'


def _p(inner: str = "") -> str:
    return f'<p style="margin:0;padding:0;line-height:normal;{FONT}font-size:10pt;">{inner or "&nbsp;"}</p>'


def _is_target(line: str, target: str) -> bool:
    return bool(target) and target.lower() in line.lower()


def render_email(req: ProfileRequest, expert_code: str, career: CareerSummary, comment: str,
                 availability: str, vqs: list[str]) -> str:
    t = TEXT[req.locale]
    target = req.target_company.strip()
    h: list[str] = [_p(_run(t["greet"](req.recipient))),
                    _p(_run(t["intro"](req.client_label, req.user_name.strip(), target))), _p()]

    h.append(_p(_run(f"[{target}]", b=True, size=15, hl="turquoise")))
    h.append(_p())
    code = _run(expert_code, u=True, color="#0000FF")

    if req.style == "standard":
        h.append(_p(_run("Expert Code: ", b=True) + code))
        cur_t = _is_target(career.current_line, target)
        hl = "yellow" if cur_t else None
        h.append(_p(_run("Current: ", b=True, hl=hl) + _run(career.current_line, b=cur_t, hl=hl)))
    elif career.matches_target:
        h.append(_p(_run("Expert ID: ", b=True) + code))
        h.append(_p(_run("Current: ", b=True, hl="yellow") + _run(career.current_line, b=True, hl="yellow")))
    else:  # clearance style: the clearance line goes ABOVE the expert id
        h.append(_p(_run("Clearance: ", b=True, u=True) + _run(career.current_line, u=True)))
        h.append(_p(_run("Expert ID: ", b=True) + code))

    former_idx = next((i for i, pl in enumerate(career.past_lines) if not pl.still_current), None)
    for i, pl in enumerate(career.past_lines):
        tgt = _is_target(pl.text, target)
        inner = _run("Former: ", b=True, hl="yellow" if tgt else None) if i == former_idx else ""
        inner += _run(pl.text, b=tgt, hl="yellow" if tgt else None)
        h.append(_p(inner))

    h.append(_p(_run("Comment:", b=True)))
    h.append(_p(_run(" ".join(comment.split()))))
    h.append(_p(_run("Rate: ", b=True) + _run(req.rate + " ") + _run("per hour", i=True)))
    h.append(_p(_run("Availability: ", b=True) + (_run(availability, b=True, color="#FF0000") if availability else "")))
    h.append(_p(_run("VQs:", b=True)))
    prefix = "Q" if req.style == "standard" else ""
    for i, q in enumerate(vqs, 1):
        h.append(_p(_run(f"{prefix}{i}. {' '.join(q.split())}")))

    h += [_p(), _p(_run(t["thanks"])), _p(_run(req.sender_signoff))]
    return "".join(h)
