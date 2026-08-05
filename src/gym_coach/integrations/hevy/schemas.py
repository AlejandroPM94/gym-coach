from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HevyModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class UserInfo(HevyModel):
    id: str | None = None
    name: str | None = None
    url: str | None = None


class UserInfoResponse(HevyModel):
    data: UserInfo


class RepRange(HevyModel):
    start: int
    end: int


class HevySet(HevyModel):
    index: int | None = None
    set_type: str | None = Field(default=None, validation_alias="type", serialization_alias="type")
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: float | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    custom_metric: float | None = None
    rep_range: RepRange | None = None


class Exercise(HevyModel):
    index: int | None = None
    title: str
    notes: str | None = None
    exercise_template_id: str
    superset_id: int | None = None
    rest_seconds: int | None = None
    sets: list[HevySet] = Field(default_factory=list)


class Workout(HevyModel):
    id: str
    title: str
    description: str | None = None
    routine_id: str | None = None
    start_time: datetime
    end_time: datetime
    updated_at: datetime | None = None
    created_at: datetime | None = None
    exercises: list[Exercise] = Field(default_factory=list)


class Routine(HevyModel):
    id: str
    title: str
    folder_id: int | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None
    exercises: list[Exercise] = Field(default_factory=list)


class ExerciseTemplate(HevyModel):
    id: str
    title: str
    type: str
    primary_muscle_group: str
    secondary_muscle_groups: list[str] = Field(default_factory=list)
    equipment: str | None = None
    is_custom: bool | None = None


class PageMetadata(HevyModel):
    page: int = Field(ge=1)
    page_count: int = Field(ge=0)


class WorkoutPage(PageMetadata):
    workouts: list[Workout]


class RoutinePage(PageMetadata):
    routines: list[Routine]


class ExerciseTemplatePage(PageMetadata):
    exercise_templates: list[ExerciseTemplate]


JsonObject = dict[str, Any]
