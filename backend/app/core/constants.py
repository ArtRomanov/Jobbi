from enum import Enum


class ApplicationStatus(str, Enum):
    RESEARCHING = "researching"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


DEFAULT_APPLICATION_STATUS = ApplicationStatus.RESEARCHING
