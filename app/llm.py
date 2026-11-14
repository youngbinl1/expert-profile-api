"""Thin wrapper around the Anthropic API plus the two prompts the service needs.

Every public function degrades gracefully: if no API key is configured, or the call fails, the
caller gets a deterministic fallback instead of an exception.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("profile-api")


class LLM:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str, max_tokens: int = 600) -> str:
        import anthropic  # imported lazily so tests/mock mode never need the network

        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()


def dominant_language(text: str) -> str:
    """'ko' if the text has at least as many Hangul letters as Latin letters, else 'en'."""
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "ko" if hangul >= latin else "en"


def _comment_prompt(target: str, career_text: str, vq_text: str, lang: str) -> str:
    if lang == "ko":
        style = ("한국어로, 줄바꿈 없이 하나의 문단으로 작성. 공백 포함 250~300자 내외. "
                 "타겟사와 VQ 주제에 직접 관련된 경력을 중심으로, 이 전문가가 VQ와 인터뷰 주제에 "
                 "잘 답변할 수 있는 사람임을 보여주는 어조.")
    else:
        style = ("Write in English as ONE paragraph with no line breaks, about 250-300 characters "
                 "(roughly 45-55 words). Focus on experience directly related to the target company and "
                 "the VQs, showing why this expert can answer them well.")
    return f"""You help a research associate at an expert network write a short career comment.
Use ONLY the career data below. Never invent roles, companies or facts.

[Target company]
{target}

[Career data]
{career_text}

[Screening questions (VQs)]
{vq_text or "(none)"}

[Style]
{style}

Output only the paragraph itself, with no greeting or explanation."""


def generate_comment(llm: LLM, target: str, current_line: str, past_lines: list[str],
                     vqs: list[str]) -> tuple[str, str | None]:
    """Return (comment, warning). The warning is set when the fallback template was used."""
    career_text = "\n".join([current_line, *past_lines]).strip()
    lang = dominant_language(career_text)
    vq_text = "\n".join(f"{i}. {q}" for i, q in enumerate(vqs, 1))

    if llm.enabled:
        try:
            text = llm.complete(_comment_prompt(target, career_text, vq_text, lang), 600)
            return " ".join(text.split()), None
        except Exception as exc:  # network error, quota, bad key, ...
            log.warning("comment generation failed: %s", exc)
            warning = "Comment generation failed; a template comment was used instead."
    else:
        warning = "No LLM key configured; a template comment was used instead."

    topic = vqs[0] if vqs else target
    if lang == "ko":
        text = (f"{current_line.split(',')[0] if current_line else '해당 전문가'} 경력을 바탕으로 "
                f"{target} 관련 업무와 \"{topic}\" 주제에 대해 실무 관점의 답변이 가능합니다.")
    else:
        role = current_line.split(",")[0] if current_line else "This expert"
        text = (f"{role} with hands-on experience relevant to {target}, able to discuss "
                f"\"{topic}\" from a practitioner's perspective.")
    return text, warning
