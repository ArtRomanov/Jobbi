from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonalInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None


class WorkExperienceEntry(BaseModel):
    company: str
    role: str
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None


class EducationEntry(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_year: str | None = None
    end_year: str | None = None
    description: str | None = None


class CvCreate(BaseModel):
    name: str = Field(min_length=1)
    personal_info: PersonalInfo | None = None
    summary: str | None = None
    work_experience: list[WorkExperienceEntry] | None = None
    education: list[EducationEntry] | None = None
    skills: str | None = None
    languages: str | None = None


class CvUpdate(BaseModel):
    name: str | None = None
    personal_info: PersonalInfo | None = None
    summary: str | None = None
    work_experience: list[WorkExperienceEntry] | None = None
    education: list[EducationEntry] | None = None
    skills: str | None = None
    languages: str | None = None


class CvRead(BaseModel):
    id: str
    name: str
    personal_info: PersonalInfo | None
    summary: str | None
    work_experience: list[WorkExperienceEntry] | None
    education: list[EducationEntry] | None
    skills: str | None
    languages: str | None
    linked_applications_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CvDuplicateRequest(BaseModel):
    name: str | None = None
