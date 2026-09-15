from decimal import Decimal

import pytest
from pydantic import ValidationError

from gym_coach.nutrition.calculations import scale, total
from gym_coach.nutrition.schemas import FoodInput, MealInput, Nutrients, Portion


def test_scaling_preserves_label_energy_and_unknown_fiber() -> None:
    label = Nutrients(energy_kcal="60", protein_g="4", carbohydrate_g="5", fat_g="3")
    portion = scale(label, Decimal("2.5"))
    assert portion.energy_kcal == Decimal("150")
    assert portion.protein_g == Decimal("10")
    assert portion.fiber_g is None
    assert total([portion, label]).energy_kcal == Decimal("210")
    assert total([portion, label]).fiber_g is None
    assert total([]).energy_kcal == 0


@pytest.mark.parametrize("number", ["-1", "NaN", "Infinity"])
def test_invalid_nutrients_rejected(number: str) -> None:
    with pytest.raises(ValidationError):
        Nutrients(energy_kcal=number, protein_g="1", carbohydrate_g="1", fat_g="1")


def test_units_dates_and_provenance_are_required() -> None:
    with pytest.raises(ValidationError):
        Portion.model_validate(
            {"item_id": "00000000-0000-0000-0000-000000000001", "quantity": 0, "unit": "g"}
        )
    with pytest.raises(ValidationError):
        MealInput.model_validate(
            {
                "consumed_at": "2026-09-14T10:00:00",
                "meal": "lunch",
                "items": [
                    {
                        "item_id": "00000000-0000-0000-0000-000000000001",
                        "quantity": 100,
                        "unit": "g",
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        FoodInput.model_validate(
            {
                "name": "Rice",
                "basis_unit": "g",
                "state": "raw",
                "source": "reference",
                "nutrients_per_100": {
                    "energy_kcal": 100,
                    "protein_g": 1,
                    "carbohydrate_g": 20,
                    "fat_g": 1,
                },
            }
        )
