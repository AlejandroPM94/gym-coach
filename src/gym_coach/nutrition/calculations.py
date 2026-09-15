from decimal import Decimal

from gym_coach.nutrition.schemas import Nutrients


def scale(value: Nutrients, factor: Decimal) -> Nutrients:
    return Nutrients.model_validate(
        {
            key: number * factor if number is not None else None
            for key, number in value.model_dump().items()
        }
    )


def total(values: list[Nutrients]) -> Nutrients:
    return Nutrients(
        energy_kcal=sum((v.energy_kcal for v in values), Decimal(0)),
        protein_g=sum((v.protein_g for v in values), Decimal(0)),
        carbohydrate_g=sum((v.carbohydrate_g for v in values), Decimal(0)),
        fat_g=sum((v.fat_g for v in values), Decimal(0)),
        fiber_g=(
            sum((v.fiber_g or Decimal(0) for v in values), Decimal(0))
            if all(v.fiber_g is not None for v in values)
            else None
        ),
    )
