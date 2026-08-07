from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


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


class UpdatedWorkoutEvent(HevyModel):
    type: Literal["updated"]
    workout: Workout


class DeletedWorkoutEvent(HevyModel):
    type: Literal["deleted"]
    id: str
    deleted_at: datetime


WorkoutEvent = Annotated[
    UpdatedWorkoutEvent | DeletedWorkoutEvent,
    Field(discriminator="type"),
]


class WorkoutEventPage(PageMetadata):
    events: list[WorkoutEvent] = Field(
        validation_alias=AliasChoices("workouts", "events"),
        serialization_alias="workouts",
    )


class RoutinePage(PageMetadata):
    routines: list[Routine]


class RoutineResponse(HevyModel):
    routine: Routine

    @field_validator("routine", mode="before")
    @classmethod
    def _accept_single_item_list(cls, value: object) -> object:
        """Accept Hevy's object and one-item-list response variants."""
        if isinstance(value, list):
            if len(value) != 1:
                raise ValueError("routine response list must contain exactly one item")
            return value[0]
        return value


class ExerciseTemplatePage(PageMetadata):
    exercise_templates: list[ExerciseTemplate]


JsonObject = dict[str, Any]


class RoutineWriteSet(HevyModel):
    set_type: Literal["warmup", "normal", "failure", "dropset"] = Field(
        default="normal", serialization_alias="type"
    )
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    custom_metric: float | None = None
    rep_range: RepRange | None = None


class RoutineWriteExercise(HevyModel):
    exercise_template_id: str
    superset_id: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[RoutineWriteSet]


class RoutineWriteData(HevyModel):
    title: str
    folder_id: int | None = None
    notes: str | None = None
    exercises: list[RoutineWriteExercise]


class RoutineWriteRequest(HevyModel):
    routine: RoutineWriteData
