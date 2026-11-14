from typing import Literal

from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    style: Literal["standard", "clearance"] = Field(
        "standard",
        description="'standard': always shows Current/Former. 'clearance': shows Current only if the "
                    "expert's current employer is the target company, otherwise a Clearance line.",
    )
    locale: Literal["ko", "en"] = "ko"
    client_label: str = Field("Client A", max_length=60)
    recipient: str = Field("", max_length=40)
    user_name: str = Field("", max_length=60)
    sender_signoff: str = Field("", max_length=60)
    target_company: str = Field(..., min_length=1, max_length=120)
    expert_code: str = Field(..., min_length=1, max_length=40)
    career_text: str = Field(..., min_length=1, max_length=20000)
    rate: str = Field("", max_length=60)
    availability_text: str = Field("", max_length=2000)
    vq_text: str = Field("", max_length=8000)


class ProfileResponse(BaseModel):
    id: str
    html: str
    comment: str
    availability_kst: str
    career_entries: int
    warnings: list[str]
