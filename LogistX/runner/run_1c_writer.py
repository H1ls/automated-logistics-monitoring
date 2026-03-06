import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]  # .../pet.project
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from LogistX.controllers.oneCReportImporter import OneCReportImporter
from LogistX.controllers.twoCRaceWriter import TwoCRaceWriter


def log(m): print(m)


def ensure_rdp():
    imp = OneCReportImporter(log_func=log)
    return imp._activate_rdp()


def main():
    # writer = OneCRaceWriter(rdp_activator=ensure_rdp, log_func=log)
    writer = TwoCRaceWriter(rdp_activator=ensure_rdp, log_func=log)

    payload = {
        "load_in": "26.02.2026 15:08:10",
        "load_out": "26.02.2026 17:28:46",
        "unload_in": "27.02.2026 13:23:39",
        "unload_out": "27.02.2026 14:23:39",
    }
    sd ="Рейс (уэ) ВТ000001968 от 26.02.2026 11:23:39"
    writer.open_race_and_read_departure_dt(sd)


if __name__ == "__main__":
    main()
