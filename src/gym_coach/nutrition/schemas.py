from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Amount = Annotated[Decimal, Field(gt=0, le=100_000, allow_inf_nan=False)]
Nutrient = Annotated[Decimal, Field(ge=0, le=100_000, allow_inf_nan=False)]


class NutritionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Nutrients(NutritionModel):
    energy_kcal: Nutrient
    protein_g: Nutrient
    carbohydrate_g: Nutrient
    fat_g: Nutrient
    fiber_g: Nutrient | None = None


class FoodInput(NutritionModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, pattern=r"^\d{8,14}$")
    state: Literal["raw", "cooked", "as_sold"]
    basis_unit: Literal["g", "ml"]
    serving_size: Amount | None = None
    serving_unit: Literal["g", "ml"] | None = None
    nutrients_per_100: Nutrients
    source: Literal["label", "reference", "estimate"]
    source_reference: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def valid_serving(self) -> "FoodInput":
        if (self.serving_size is None) != (self.serving_unit is None):
            raise ValueError("Serving size and unit must be provided together")
        if self.serving_unit is not None and self.serving_unit != self.basis_unit:
            raise ValueError("Serving unit must match the food basis unit")
        return self


class Portion(NutritionModel):
    item_id: UUID
    quantity: Amount
    unit: Literal["g", "ml", "serving"]


class RecipeInput(NutritionModel):
    name: str = Field(min_length=1, max_length=200)
    ingredients: list[Portion] = Field(min_length=1, max_length=100)
    servings: Amount
    cooked_weight_g: Amount | None = None


class MealInput(NutritionModel):
    consumed_at: AwareDatetime
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    items: list[Portion] = Field(min_length=1, max_length=100)
    estimated_quantity: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class ItemSnapshot(NutritionModel):
    portion: Portion
    name: str
    nutrients: Nutrients
    estimated: bool


class MealPreview(NutritionModel):
    data: MealInput
    items: list[ItemSnapshot]
    totals: Nutrients
    estimated: bool


class CatalogueItem(NutritionModel):
    id: UUID
    name: str
    kind: Literal["food", "recipe"]
    food: FoodInput | None = None
    recipe: RecipeInput | None = None
    totals: Nutrients
    estimated: bool


class MealRecord(MealPreview):
    id: UUID
    recorded_at: datetime
    voided: bool = False


class DailyNutrition(NutritionModel):
    day: date
    timezone: str
    entries: list[MealRecord]
    totals: Nutrients
    has_estimates: bool
    coverage: Literal["logged_meals_only"] = "logged_meals_only"


class VoidResult(NutritionModel):
    meal_id: UUID
    voided: Literal[True] = True
