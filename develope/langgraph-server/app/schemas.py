"""외부(Airflow)에서 들어오는 요청의 pydantic 모델. main.py에서 분리."""
from pydantic import BaseModel


class GamePick(BaseModel):
    appid: int
    name: str
    developer: str | None = None
    publisher: str | None = None
    ccu: int | None = None
    positive: int | None = None
    negative: int | None = None
    last_recommended_at: str | None = None


class WeeklyReportRequest(BaseModel):
    old_introductions: list[GamePick]
    recent_new: list[GamePick]
    recent_replays: list[GamePick]
