from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.nutrition.calculations import scale, total
from gym_coach.nutrition.schemas import (
    CatalogueItem,
    DailyNutrition,
    FoodInput,
    ItemSnapshot,
    MealInput,
    MealPreview,
    MealRecord,
    Portion,
    RecipeInput,
    VoidResult,
)
from gym_coach.persistence.models import NutritionRecord


class NutritionService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def _store(
        self,
        record_id: UUID,
        kind: str,
        name: str,
        request: dict[str, Any],
        result: dict[str, Any],
        confirmed: bool,
        consumed_at: datetime | None = None,
    ) -> NutritionRecord:
        if confirmed is not True:
            raise ValueError("Explicit confirmation of the exact nutrition record is required")
        async with self.factory.begin() as session:
            await session.execute(
                insert(NutritionRecord)
                .values(
                    id=record_id,
                    kind=kind,
                    name=name,
                    request=request,
                    result=result,
                    user_confirmed=True,
                    consumed_at=consumed_at,
                )
                .on_conflict_do_nothing(index_elements=[NutritionRecord.id])
            )
            row = await session.get(NutritionRecord, record_id)
            assert row is not None
            if row.kind != kind or row.request != request:
                raise ValueError("Request ID already used with different data")
            return row

    async def save_food(
        self,
        request_id: UUID,
        food: FoodInput,
        user_confirmed: bool,
    ) -> CatalogueItem:
        result = CatalogueItem(
            id=request_id,
            name=food.name,
            kind="food",
            food=food,
            totals=food.nutrients_per_100,
            estimated=food.source == "estimate",
        )
        row = await self._store(
            request_id,
            "food",
            food.name,
            food.model_dump(mode="json"),
            result.model_dump(mode="json"),
            user_confirmed,
        )
        return CatalogueItem.model_validate(row.result)

    async def search(self, query: str) -> list[CatalogueItem]:
        if not 1 <= len(query.strip()) <= 200:
            raise ValueError("Search must contain 1 to 200 characters")
        async with self.factory() as session:
            rows = await session.scalars(
                select(NutritionRecord)
                .where(
                    NutritionRecord.kind.in_(["food", "recipe"]),
                    or_(
                        NutritionRecord.name.icontains(query.strip(), autoescape=True),
                        NutritionRecord.request["barcode"].as_string() == query.strip(),
                    ),
                )
                .order_by(NutritionRecord.created_at.desc(), NutritionRecord.id)
                .limit(25)
            )
            return [CatalogueItem.model_validate(row.result) for row in rows]

    async def _resolve(self, portions: list[Portion]) -> list[ItemSnapshot]:
        snapshots: list[ItemSnapshot] = []
        async with self.factory() as session:
            for portion in portions:
                row = await session.get(NutritionRecord, portion.item_id)
                if row is None or row.kind not in {"food", "recipe"}:
                    raise ValueError("Unknown food or recipe ID; search the catalogue first")
                item = CatalogueItem.model_validate(row.result)
                if item.food is not None:
                    if portion.unit == "serving" and item.food.serving_size is not None:
                        factor = portion.quantity * item.food.serving_size / Decimal(100)
                    elif portion.unit != item.food.basis_unit:
                        raise ValueError("Portion unit must match the food label basis")
                    else:
                        factor = portion.quantity / Decimal(100)
                else:
                    assert item.recipe is not None
                    if portion.unit == "serving":
                        factor = portion.quantity / item.recipe.servings
                    elif portion.unit == "g" and item.recipe.cooked_weight_g is not None:
                        factor = portion.quantity / item.recipe.cooked_weight_g
                    else:
                        raise ValueError("Recipe requires servings or a known cooked weight")
                snapshots.append(
                    ItemSnapshot(
                        portion=portion,
                        name=item.name,
                        nutrients=scale(item.totals, factor),
                        estimated=item.estimated,
                    )
                )
        return snapshots

    async def save_recipe(
        self,
        request_id: UUID,
        recipe: RecipeInput,
        user_confirmed: bool,
    ) -> CatalogueItem:
        items = await self._resolve(recipe.ingredients)
        result = CatalogueItem(
            id=request_id,
            name=recipe.name,
            kind="recipe",
            recipe=recipe,
            totals=total([i.nutrients for i in items]),
            estimated=any(i.estimated for i in items),
        )
        row = await self._store(
            request_id,
            "recipe",
            recipe.name,
            recipe.model_dump(mode="json"),
            result.model_dump(mode="json"),
            user_confirmed,
        )
        return CatalogueItem.model_validate(row.result)

    async def preview(self, meal: MealInput) -> MealPreview:
        items = await self._resolve(meal.items)
        return MealPreview(
            data=meal,
            items=items,
            totals=total([i.nutrients for i in items]),
            estimated=meal.estimated_quantity or any(i.estimated for i in items),
        )

    async def log_meal(
        self,
        request_id: UUID,
        meal: MealInput,
        user_confirmed: bool,
    ) -> MealRecord:
        preview = await self.preview(meal)
        row = await self._store(
            request_id,
            "meal",
            meal.meal,
            meal.model_dump(mode="json"),
            preview.model_dump(mode="json"),
            user_confirmed,
            meal.consumed_at,
        )
        return MealRecord(**row.result, id=row.id, recorded_at=row.created_at)

    async def void(self, meal_id: UUID, reason: str, user_confirmed: bool) -> VoidResult:
        if not 1 <= len(reason.strip()) <= 1000:
            raise ValueError("A correction reason is required (1 to 1000 characters)")
        async with self.factory() as session:
            row = await session.get(NutritionRecord, meal_id)
            if row is None or row.kind != "meal":
                raise ValueError("Unknown meal ID")
        await self._store(
            uuid5(NAMESPACE_URL, f"gym-coach:nutrition:void:{meal_id}"),
            "void",
            "meal correction",
            {"meal_id": str(meal_id), "reason": reason},
            {"meal_id": str(meal_id)},
            user_confirmed,
        )
        return VoidResult(meal_id=meal_id)

    async def daily(self, day: date, timezone: str) -> DailyNutrition:
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        start = datetime.combine(day, time.min, zone)
        end = datetime.combine(day + timedelta(days=1), time.min, zone)
        async with self.factory() as session:
            rows = list(
                await session.scalars(
                    select(NutritionRecord)
                    .where(
                        NutritionRecord.kind == "meal",
                        NutritionRecord.consumed_at >= start,
                        NutritionRecord.consumed_at < end,
                    )
                    .order_by(NutritionRecord.consumed_at, NutritionRecord.id)
                )
            )
            void_ids = [uuid5(NAMESPACE_URL, f"gym-coach:nutrition:void:{row.id}") for row in rows]
            voids = list(
                await session.scalars(
                    select(NutritionRecord).where(NutritionRecord.id.in_(void_ids))
                )
            )
        excluded = {row.result["meal_id"] for row in voids}
        entries = [
            MealRecord(
                **row.result, id=row.id, recorded_at=row.created_at, voided=str(row.id) in excluded
            )
            for row in rows
        ]
        active = [entry for entry in entries if not entry.voided]
        return DailyNutrition(
            day=day,
            timezone=timezone,
            entries=entries,
            totals=total([entry.totals for entry in active]),
            has_estimates=any(entry.estimated for entry in active),
        )
