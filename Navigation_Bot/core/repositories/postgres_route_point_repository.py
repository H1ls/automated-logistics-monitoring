from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PostgresRoutePointRepository:
    connection: Any

    def sync_route_points(self, task_id: int, point_type: str, points: list[Any], processed_unloads: list[bool],
                          source: str, ) -> None:
        existing = self._existing_route_points(task_id, point_type)
        seen_sequences: set[int] = set()

        for point in points:
            sequence = int(point.sequence)
            seen_sequences.add(sequence)
            is_processed = False
            if point.kind == "unload":
                unload_idx = max(sequence - 1, 0)
                if unload_idx < len(processed_unloads):
                    is_processed = bool(processed_unloads[unload_idx])

            old = existing.get(sequence)
            new_values = {"location": point.address or "",
                          "scheduled_time": point.planned_datetime_text() or "",
                          "comment": point.comment or "",
                          "is_processed": is_processed,
                          "latitude": point.latitude,
                          "longitude": point.longitude,
                          "geocoding_source": point.geocoding_source or (
                              "parsed" if point.latitude is not None and point.longitude is not None else "" ),
                          }

            if old is None:
                geocoded_at = "now" if new_values["latitude"] is not None and new_values[
                    "longitude"] is not None else None
                self.connection.execute(
                    """
                    INSERT INTO route_points (
                        task_id, sequence, point_type, location, scheduled_time,
                        comment, is_processed, latitude, longitude, geocoding_source, geocoded_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz)
                    """,
                    (
                        task_id,
                        sequence,
                        point.kind,
                        new_values["location"],
                        new_values["scheduled_time"],
                        new_values["comment"],
                        new_values["is_processed"],
                        new_values["latitude"],
                        new_values["longitude"],
                        new_values["geocoding_source"],
                        geocoded_at,
                    ),
                )
                continue

            if not any(old[field] != new_value for field, new_value in new_values.items()):
                continue

            self.connection.execute(
                """
                UPDATE route_points
                SET location = %s,
                    scheduled_time = %s,
                    comment = %s,
                    is_processed = %s,
                    latitude = %s,
                    longitude = %s,
                    geocoding_source = %s,
                    geocoded_at = CASE
                        WHEN %s::double precision IS NOT NULL AND %s::double precision IS NOT NULL
                             AND (latitude IS DISTINCT FROM %s::double precision OR longitude IS DISTINCT FROM %s::double precision)
                        THEN CURRENT_TIMESTAMP::text
                        ELSE geocoded_at
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    new_values["location"],
                    new_values["scheduled_time"],
                    new_values["comment"],
                    new_values["is_processed"],
                    new_values["latitude"],
                    new_values["longitude"],
                    new_values["geocoding_source"],
                    new_values["latitude"],
                    new_values["longitude"],
                    new_values["latitude"],
                    new_values["longitude"],
                    old["id"],
                ),
            )

        for sequence, old in existing.items():
            if sequence not in seen_sequences:
                self.connection.execute("DELETE FROM route_points WHERE id = %s", (old["id"],))

    def _existing_route_points(self, task_id: int, point_type: str) -> dict[int, dict]:
        rows = self.connection.execute(
            """
            SELECT id, sequence, location, scheduled_time, comment, is_processed,
                   latitude, longitude, geocoding_source
            FROM route_points
            WHERE task_id = %s AND point_type = %s
            """,
            (task_id, point_type),
        ).fetchall()
        return {
            int(row["sequence"]): {
                "id": int(row["id"]),
                "location": row["location"] or "",
                "scheduled_time": row["scheduled_time"] or "",
                "comment": row["comment"] or "",
                "is_processed": bool(row["is_processed"]),
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "geocoding_source": row["geocoding_source"] or "",
            }
            for row in rows
        }
