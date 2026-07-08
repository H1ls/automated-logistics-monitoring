import json
from pathlib import Path

from Navigation_Bot.bots.route_info_parser import RouteInfoParser


DATASET_FILE = Path(__file__).parents[3] / "config" / "datasets" / "addresses.jsonl"


def _legacy_to_dataset(blocks: list[dict], prefix: str) -> list[dict]:
    result = []
    pending_comment = None
    for block in blocks:
        comment = block.get("Комментарий")
        address_key = next((key for key in block if key.startswith(f"{prefix} ")), None)
        if address_key:
            sequence = address_key.rsplit(" ", 1)[-1]
            item = {
                "Адрес": block.get(address_key),
                "Дата": block.get(f"Дата {sequence}"),
                "Время": block.get(f"Время {sequence}"),
            }
            if pending_comment:
                item["Комментарий"] = pending_comment
                pending_comment = None
            result.append(item)
        elif comment:
            pending_comment = comment

    if pending_comment and result:
        result[-1]["Комментарий"] = pending_comment
    return result


def test_route_info_parser_handles_addresses_dataset_core_fields():
    parser = RouteInfoParser()

    exact_matches = 0
    core_matches = 0
    total = 0
    for line_number, line in enumerate(DATASET_FILE.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        actual = _legacy_to_dataset(parser.parse(row["input"], "Выгрузка"), "Выгрузка")
        expected = row["output"]
        total += 1

        if actual == expected:
            exact_matches += 1

        if len(actual) == len(expected) and all(
            actual_item.get("Дата") == expected_item.get("Дата")
            and actual_item.get("Время") == expected_item.get("Время")
            and actual_item.get("Адрес")
            for actual_item, expected_item in zip(actual, expected)
        ):
            core_matches += 1

    assert total == 17
    assert exact_matches >= 7
    assert core_matches >= 12
