import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

import pytest

from gym_coach.integrations.health_connect.export import (
    HealthConnectExportError,
    parse_health_connect_export,
)

EPOCH = date(1970, 1, 1)


def _export(tmp_path: Path, *, version: int = 26) -> Path:
    database = tmp_path / "fixture.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            f"""
            PRAGMA user_version = {version};
            CREATE TABLE application_info_table (
                row_id INTEGER PRIMARY KEY,
                package_name TEXT NOT NULL
            );
            CREATE TABLE steps_record_table (
                app_info_id INTEGER NOT NULL,
                local_date INTEGER NOT NULL,
                count INTEGER NOT NULL
            );
            CREATE TABLE sleep_session_record_table (
                row_id INTEGER PRIMARY KEY,
                app_info_id INTEGER NOT NULL,
                local_date INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL
            );
            CREATE TABLE sleep_stages_table (
                parent_key INTEGER NOT NULL, stage_start_time INTEGER NOT NULL,
                stage_end_time INTEGER NOT NULL, stage_type INTEGER NOT NULL
            );
            CREATE TABLE exercise_session_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL,
                start_time INTEGER NOT NULL, end_time INTEGER NOT NULL,
                exercise_type INTEGER NOT NULL
            );
            CREATE TABLE distance_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL, distance REAL
            );
            CREATE TABLE total_calories_burned_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL, energy REAL
            );
            CREATE TABLE heart_rate_record_table (
                row_id INTEGER PRIMARY KEY, app_info_id INTEGER NOT NULL,
                local_date INTEGER NOT NULL
            );
            CREATE TABLE heart_rate_record_series_table (
                parent_key INTEGER NOT NULL, beats_per_minute INTEGER NOT NULL
            );
            CREATE TABLE resting_heart_rate_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL,
                beats_per_minute INTEGER NOT NULL
            );
            CREATE TABLE heart_rate_variability_rmssd_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL,
                heart_rate_variability_millis REAL NOT NULL
            );
            CREATE TABLE oxygen_saturation_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL, percentage REAL NOT NULL
            );
            CREATE TABLE vo2_max_record_table (
                app_info_id INTEGER NOT NULL, local_date INTEGER NOT NULL,
                vo2_milliliters_per_minute_kilogram REAL NOT NULL
            );
            CREATE TABLE weight_record_table (
                row_id INTEGER PRIMARY KEY,
                uuid BLOB NOT NULL,
                app_info_id INTEGER NOT NULL,
                local_date INTEGER NOT NULL,
                time INTEGER NOT NULL,
                weight REAL NOT NULL
            );
            CREATE TABLE body_fat_record_table (
                row_id INTEGER PRIMARY KEY,
                app_info_id INTEGER NOT NULL,
                time INTEGER NOT NULL,
                percentage REAL NOT NULL
            );
            CREATE TABLE lean_body_mass_record_table (
                row_id INTEGER PRIMARY KEY, app_info_id INTEGER NOT NULL,
                time INTEGER NOT NULL, mass REAL NOT NULL
            );
            CREATE TABLE body_water_mass_record_table (
                row_id INTEGER PRIMARY KEY, app_info_id INTEGER NOT NULL,
                time INTEGER NOT NULL, body_water_mass REAL NOT NULL
            );
            CREATE TABLE bone_mass_record_table (
                row_id INTEGER PRIMARY KEY, app_info_id INTEGER NOT NULL,
                time INTEGER NOT NULL, mass REAL NOT NULL
            );
            CREATE TABLE basal_metabolic_rate_record_table (
                row_id INTEGER PRIMARY KEY, app_info_id INTEGER NOT NULL,
                time INTEGER NOT NULL, basal_metabolic_rate REAL NOT NULL
            );
            """
        )
        day = (date(2026, 9, 14) - EPOCH).days
        connection.executemany(
            "INSERT INTO application_info_table VALUES (?, ?)",
            [
                (1, "com.sec.android.app.shealth"),
                (2, "com.google.android.apps.fitness"),
                (3, "com.health.openscale.sync"),
            ],
        )
        connection.executemany(
            "INSERT INTO steps_record_table VALUES (?, ?, ?)",
            [(1, day, 4_000), (1, day, 2_000), (2, day, 90_000)],
        )
        connection.executemany(
            "INSERT INTO sleep_session_record_table VALUES (?, ?, ?, ?, ?)",
            [(1, 1, day, 0, 7 * 60 * 60 * 1000), (2, 2, day, 0, 20 * 60 * 60 * 1000)],
        )
        connection.executemany(
            "INSERT INTO sleep_stages_table VALUES (?, ?, ?, ?)",
            [(1, 0, 60 * 60 * 1000, 1), (1, 60 * 60 * 1000, 7 * 60 * 60 * 1000, 4)],
        )
        connection.execute(
            "INSERT INTO exercise_session_record_table VALUES (?, ?, ?, ?, ?)",
            (1, day, 0, 30 * 60 * 1000, 53),
        )
        connection.execute("INSERT INTO distance_record_table VALUES (?, ?, ?)", (1, day, 4200))
        connection.execute(
            "INSERT INTO total_calories_burned_record_table VALUES (?, ?, ?)",
            (1, day, 650000),
        )
        connection.execute("INSERT INTO heart_rate_record_table VALUES (?, ?, ?)", (1, 1, day))
        connection.executemany(
            "INSERT INTO heart_rate_record_series_table VALUES (?, ?)", [(1, 60), (1, 100)]
        )
        connection.execute(
            "INSERT INTO resting_heart_rate_record_table VALUES (?, ?, ?)", (1, day, 55)
        )
        connection.execute(
            "INSERT INTO heart_rate_variability_rmssd_record_table VALUES (?, ?, ?)",
            (1, day, 42.5),
        )
        connection.executemany(
            "INSERT INTO oxygen_saturation_record_table VALUES (?, ?, ?)",
            [(1, day, 96), (1, day, 98)],
        )
        connection.execute("INSERT INTO vo2_max_record_table VALUES (?, ?, ?)", (1, day, 41.8))
        measured_at = int(datetime(2026, 9, 14, 6, tzinfo=UTC).timestamp() * 1000)
        connection.executemany(
            "INSERT INTO weight_record_table VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, uuid4().bytes, 3, day, measured_at, 80_000),
                (2, uuid4().bytes, 2, day, measured_at, 300_000),
            ],
        )
        connection.execute(
            "INSERT INTO body_fat_record_table VALUES (?, ?, ?, ?)",
            (1, 3, measured_at, 18.5),
        )
        connection.execute(
            "INSERT INTO lean_body_mass_record_table VALUES (?, ?, ?, ?)",
            (1, 3, measured_at, 65200),
        )
        connection.execute(
            "INSERT INTO body_water_mass_record_table VALUES (?, ?, ?, ?)",
            (1, 3, measured_at, 44800),
        )
        connection.execute(
            "INSERT INTO bone_mass_record_table VALUES (?, ?, ?, ?)",
            (1, 3, measured_at, 3200),
        )
        connection.execute(
            "INSERT INTO basal_metabolic_rate_record_table VALUES (?, ?, ?, ?)",
            (1, 3, measured_at, 80),
        )
        connection.commit()
    finally:
        connection.close()
    archive = tmp_path / "Health Connect.zip"
    with ZipFile(archive, "w", compression=ZIP_STORED) as bundle:
        bundle.write(database, "health_connect_export.db")
    return archive


def test_export_parser_filters_samsung_and_aggregates_recent_days(tmp_path: Path) -> None:
    batch = parse_health_connect_export(
        _export(tmp_path),
        request_id=uuid4(),
        observed_at=datetime(2026, 9, 15, 8, tzinfo=UTC),
        timezone="Europe/Madrid",
    )
    assert len(batch.days) == 1
    assert batch.days[0].day == date(2026, 9, 14)
    assert batch.days[0].steps == 6_000
    assert batch.days[0].sleep_session_minutes == 420
    assert batch.days[0].sleep_asleep_minutes == 360
    assert batch.days[0].sleep_awake_minutes == 60
    assert batch.days[0].exercise_minutes_by_type == {"walking": Decimal(30)}
    assert batch.days[0].distance_meters == 4200
    assert batch.days[0].total_energy_kcal == 650
    assert batch.days[0].mean_heart_rate_bpm == 80
    assert batch.days[0].mean_oxygen_saturation_percent == 97
    assert batch.days[0].vo2_max_ml_min_kg == Decimal("41.8")
    assert batch.days[0].source == "health_connect_samsung"
    assert len(batch.body_measurements) == 1
    measurement = batch.body_measurements[0]
    assert measurement.weight_kg == 80
    assert measurement.body_fat_percent == Decimal("18.5")
    assert measurement.body_fat_method == "consumer_bia"
    assert measurement.lean_body_mass_kg == Decimal("65.2")
    assert measurement.body_water_mass_kg == Decimal("44.8")
    assert measurement.bone_mass_kg == Decimal("3.2")
    assert measurement.basal_metabolic_rate_kcal.quantize(Decimal("0.01")) == Decimal("1652.01")
    assert measurement.source == "health_connect_openscale"


def test_export_parser_rejects_unknown_schema_version(tmp_path: Path) -> None:
    with pytest.raises(HealthConnectExportError, match="schema version: 27"):
        parse_health_connect_export(
            _export(tmp_path, version=27),
            request_id=uuid4(),
            observed_at=datetime(2026, 9, 15, 8, tzinfo=UTC),
            timezone="Europe/Madrid",
        )


def test_export_parser_rejects_unexpected_archive_layout(tmp_path: Path) -> None:
    archive = tmp_path / "Health Connect.zip"
    with ZipFile(archive, "w", compression=ZIP_STORED) as bundle:
        bundle.writestr("../health_connect_export.db", b"unsafe")
    with pytest.raises(HealthConnectExportError, match="layout"):
        parse_health_connect_export(
            archive,
            request_id=uuid4(),
            observed_at=datetime(2026, 9, 15, 8, tzinfo=UTC),
            timezone="Europe/Madrid",
        )
