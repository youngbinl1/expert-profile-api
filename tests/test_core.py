from datetime import datetime

from app.availability import format_slot, to_kst
from app.career import (location_to_country, normalize_expert_code, parse_career, parse_vqs, summarize)
from app.llm import LLM, dominant_language, generate_comment
from app.sample_data import samples

CAREER = """Director of Supply Chain
Helio Dynamics (Mar 2021 - Now, 5 years)
Austin, TX
Current role
Senior Manager
Orbitek Labs (Jun 2016 - Feb 2021, 4 years)
Eindhoven, Netherlands
Led procurement.
Analyst
Lumora Systems (Aug 2012 - May 2016, 3 years)
Singapore
Planning."""


def test_parse_career_blocks():
    e = parse_career(CAREER)
    assert [x.company for x in e] == ["Helio Dynamics", "Orbitek Labs", "Lumora Systems"]
    assert e[0].is_current and not e[1].is_current
    assert e[1].note == "Led procurement."


def test_country_resolution():
    un: list[str] = []
    assert location_to_country("Austin, TX", un) == "United States"
    assert location_to_country("Eindhoven, Netherlands", un) == "Netherlands"
    assert location_to_country("Hong Kong", un) == "Hong Kong"
    assert location_to_country("Nowhereville, Zzzland", un) == "Nowhereville, Zzzland"
    assert un == ["Nowhereville, Zzzland"]


def test_current_matches_target_even_if_not_first():
    raw = (
        "Advisor\nOther Corp (Jan 2024 - Now, 2 years)\nLondon, United Kingdom\nx\n"
        "Engineer\nHelio Dynamics (Jan 2020 - Now, 6 years)\nAustin, TX\ny"
    )
    s = summarize(parse_career(raw), "helio dynamics")
    assert s.matches_target and "Helio Dynamics" in s.current_line
    assert any("Other Corp" in p.text for p in s.past_lines)


def test_current_elsewhere_and_no_current_and_dedup():
    s = summarize(parse_career(CAREER), "Orbitek Labs")
    assert not s.matches_target and "Helio Dynamics" in s.current_line
    former_only = "Analyst\nLumora Systems (Aug 2012 - May 2016, 3 years)\nSingapore\nx"
    assert summarize(parse_career(former_only), "Lumora").current_line == "Freelancer, Self-employed,"
    dup = former_only + "\n" + former_only
    assert len(summarize(parse_career(dup), "x").past_lines) == 1


def test_expert_code_and_vqs():
    assert normalize_expert_code("891385") == "EX-891385"
    assert normalize_expert_code("ex 12") == "EX-12"
    assert normalize_expert_code("EX-7") == "EX-7"
    assert parse_vqs("1. One\ncontinued\n2) Two\nQ3. Three") == ["One continued", "Two", "Three"]
    assert parse_vqs("just one question") == ["just one question"]
    assert parse_vqs("") == []


def test_format_slot_respects_daylight_saving():
    summer = format_slot(2026, 7, 15, "09:00", "10:00", "America/New_York")   # EDT = UTC-4
    winter = format_slot(2026, 1, 15, "09:00", "10:00", "America/New_York")   # EST = UTC-5
    assert summer == "07/15 (Wed) 22:00 - 23:00 KST"
    assert winter == "01/15 (Thu) 23:00 - 00:00 KST"
    assert format_slot(2026, 7, 15, "14:00", "15:00", "Asia/Kolkata") == "07/15 (Wed) 17:30 - 18:30 KST"
    assert format_slot(2026, 7, 15, "14:00", "15:00", None) == "07/15 (Wed) 14:00 - 15:00 KST"
    assert format_slot(2026, 7, 15, "23:00", "01:00", "Asia/Hong_Kong").endswith("00:00 - 02:00 KST")


def test_to_kst_without_llm_uses_iso_format_and_shares_timezone():
    llm = LLM("", "m")
    out = to_kst("2026-07-15 09:00-10:00 America/New_York, 2026-07-16 09:00-10:00", llm, datetime(2026, 7, 1))
    assert out == "07/15 (Wed) 22:00 - 23:00 KST, 07/16 (Thu) 22:00 - 23:00 KST"
    assert to_kst("whenever", llm) == ""


def test_dominant_language_and_template_comment():
    assert dominant_language("Senior Engineer at Acme") == "en"
    assert dominant_language("시니어 엔지니어, 삼성전자 (2020)") == "ko"
    text, warn = generate_comment(LLM("", "m"), "Helio", "Director, Helio, X", [], ["How do you source?"])
    assert "Helio" in text and warn


def test_samples_parse():
    for s in samples():
        assert parse_career(s["request"]["career_text"])


def test_dynamo_store_logic_with_fake_table():
    from app.storage import DynamoStore

    class FakeTable:
        def __init__(self):
            self.items = []

        def put_item(self, Item):
            self.items.append(Item)

        def scan(self, Limit):
            return {"Items": list(self.items)}

    store = object.__new__(DynamoStore)
    store._table, store._ttl_days = FakeTable(), 30
    store.save({"id": "a"})
    store.save({"id": "b"})
    saved = store._table.items
    assert all(isinstance(i["expires_at"], int) for i in saved)      # DynamoDB TTL attribute
    assert [i["id"] for i in store.recent(1)] == ["b"]               # newest first
