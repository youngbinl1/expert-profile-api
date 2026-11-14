"""Synthetic demo data. Every person, company and detail here is invented."""
from datetime import date, timedelta


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def samples() -> list[dict]:
    d1, d2 = _future(14), _future(15)
    vq = (
        "1. How has sourcing of precision sensor components changed over the last three years?\n"
        "2. What criteria drive supplier qualification, and how long does it usually take?\n"
        "3. How do you manage single-source supply risk in practice?"
    )
    return [
        {
            "name": "Current employee of the target (standard style)",
            "request": {
                "style": "standard", "locale": "en", "client_label": "Client A", "recipient": "Ms. Park",
                "user_name": "", "sender_signoff": "Demo Associate",
                "target_company": "Helio Dynamics", "expert_code": "100234",
                "career_text": (
                    "Director of Supply Chain\nHelio Dynamics (Mar 2021 - Now, 5 years)\nAustin, TX\nCurrent role\n"
                    "Senior Supply Chain Manager\nOrbitek Labs (Jun 2016 - Feb 2021, 4 years)\nEindhoven, Netherlands\n"
                    "Led global procurement for sensor components.\n"
                    "Operations Analyst\nLumora Systems (Aug 2012 - May 2016, 3 years)\nSingapore\nSupported demand planning."
                ),
                "rate": "450 USD",
                "availability_text": f"{d1} 09:00-10:00 America/New_York, {d2} 14:00-15:00 Europe/Berlin",
                "vq_text": vq,
            },
        },
        {
            "name": "Former employee, now elsewhere (clearance style)",
            "request": {
                "style": "clearance", "locale": "en", "client_label": "Client B", "recipient": "Mr. Kim",
                "user_name": "", "sender_signoff": "Demo Associate",
                "target_company": "Lumora Systems", "expert_code": "EX-100871",
                "career_text": (
                    "VP Procurement\nVeridian Partners (Jan 2023 - Now, 3 years)\nLondon, United Kingdom\nCurrent role\n"
                    "Head of Sourcing\nLumora Systems (Feb 2018 - Dec 2022, 4 years)\nHong Kong\nManaged Asia sourcing."
                ),
                "rate": "1.5 credit",
                "availability_text": f"{d1} 10:00-11:00 Asia/Kolkata",
                "vq_text": vq,
            },
        },
    ]
