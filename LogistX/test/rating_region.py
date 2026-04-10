import time

from PIL import Image, ImageDraw
from pathlib import Path

from LogistX.onec.uimap import UiMap
from LogistX.onec.session import OneCSession
RDP_TITLE_HINT = "176.57.78.6:2025 — Подключение к удаленному рабочему столу"
RDP_TITLE_FALLBACKS = ["Подключение к удаленному рабочему столу",
                       "Remote Desktop Connection",]

def log(msg: str):
    print(msg)
def build_session():
    logistx_dir = Path(__file__).resolve().parents[1]

    ui_map_path = logistx_dir / "config" / "onec_ui_map_v2.json"
    templates_dir = logistx_dir / "assets" / "onec_templates"
    tmp_dir = logistx_dir / "tmp"

    ui_map = UiMap(ui_map_path)

    session = OneCSession(rdp_activator=activate_rdp,
                          ui_map=ui_map,
                          templates_dir=templates_dir,
                          tmp_dir=tmp_dir,
                          log_func=log, )
    return session
def activate_rdp():
    w = find_rdp_window()
    if not w:
        raise RuntimeError("Окно RDP не найдено")

    if getattr(w, "isMinimized", False):
        w.restore()
        time.sleep(0.3)

    try:
        w.activate()
        time.sleep(0.4)
    except Exception:
        pass

    try:
        w.maximize()
        time.sleep(0.3)
    except Exception:
        pass
def find_rdp_window():
    wins = gw.getWindowsWithTitle(RDP_TITLE_HINT)
    if wins:
        return wins[0]

    for hint in RDP_TITLE_FALLBACKS:
        wins = gw.getWindowsWithTitle(hint)
        if wins:
            return wins[0]

    try:
        for title in gw.getAllTitles():
            if not title:
                continue
            if RDP_TITLE_HINT in title:
                wins = gw.getWindowsWithTitle(title)
                if wins:
                    return wins[0]
    except Exception:
        pass

    return None

session = build_session()
screen = session.screenshot_full("debug_rating_region_screen.png")
left, top, w, h = session.ui_map.get_region("rating_region")

img = Image.open(screen).convert("RGB")
draw = ImageDraw.Draw(img)
draw.rectangle((left, top, left + w, top + h), outline="red", width=3)
img.save(session.tmp_dir / "debug_rating_region_overlay.png")
print(session.tmp_dir / "debug_rating_region_overlay.png")