from __future__ import annotations


def init_processed_flags(new_data: list[dict], old_data: list[dict], loads_key: str = "Выгрузка") -> None:
    def unique_key(row: dict) -> str:
        return f'{row.get("ТС", "")}_{row.get("id", "")}'

    old_map = {unique_key(r): r.get("processed", []) for r in old_data}

    for row in new_data:
        key = unique_key(row)
        prev_flags = old_map.get(key, [])
        unloads = row.get(loads_key, []) or []

        def _is_real_point(d) -> bool:
            if not isinstance(d, dict):
                return False
            pref = f"{loads_key} "
            return any(k.startswith(pref) for k in d.keys())

        cnt = sum(_is_real_point(d) for d in unloads)
        if cnt == 0:
            row["processed"] = []
            continue

        existing_flags = row.get("processed", [])
        if len(existing_flags) == cnt:
            continue

        base_flags = existing_flags if len(existing_flags) > len(prev_flags) else prev_flags
        row["processed"] = (base_flags + [False] * cnt)[:cnt]
