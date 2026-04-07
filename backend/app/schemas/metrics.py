from datetime import date

from pydantic import BaseModel


class KpiData(BaseModel):
    total_applications: int
    active: int
    response_rate: float  # 0.0 to 1.0
    interviews: int


class PipelineEntry(BaseModel):
    status: str
    count: int


class TrendPoint(BaseModel):
    date: date
    count: int


class TrendData(BaseModel):
    granularity: str  # "daily", "weekly", "monthly"
    points: list[TrendPoint]


class MetricsResponse(BaseModel):
    range: str
    from_date: date
    to_date: date
    kpis: KpiData
    pipeline: list[PipelineEntry]
    trend: TrendData
