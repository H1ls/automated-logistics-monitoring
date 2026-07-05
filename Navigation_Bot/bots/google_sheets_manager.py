import os
import sys
import gspread

from PyQt6.QtCore import QObject, pyqtSignal
from oauth2client.service_account import ServiceAccountCredentials

from Navigation_Bot.core.json_store import JsonStore
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.logging import normalize_log_func


class GoogleSheetsManager(QObject):
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, config_key="default", log_func=None, parent=None):
        super().__init__(parent)
        self._external_log = normalize_log_func(log_func) if log_func else None

        self.config_key = config_key
        self.config_manager = JsonStore(CONFIG_JSON)

        # основные поля
        self.worksheet_index = None
        self.auth_sheet_id = None
        self.column_index = None
        self.file_path = None

        self.spreadsheet = None
        self.sheet = None
        self._worksheets_cache = []
        self.load_settings()

    def _log(self, msg: str):
        """Безопасное логирование: только через сигнал"""
        text = str(msg)
        # внешний лог, если передан
        if self._external_log:
            try:
                self._external_log(text)
            except Exception as e:
                print(f"Warning: logging failed: {e}", file=sys.stderr)
        # сигнал для GUI
        self.log_message.emit(text)

    def _create_client(self):
        """Создаёт gspread-клиент из self.creds_file"""
        if not self.creds_file or not os.path.exists(self.creds_file):
            self._log(f"❌ Файл авторизации не найден: {self.creds_file}")
            return None

        try:
            full_block = JsonStore().load_json(self.creds_file)
            creds_data = full_block.get("credentials")
            if not creds_data:
                self._log(f"❌ В файле {self.creds_file} отсутствует ключ 'credentials'")
                return None

            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_data,
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"])
            return gspread.authorize(creds)
        except Exception as e:
            self._log(f"❌ Ошибка создания клиента Google: {e}")
            return None

    def load_settings(self):
        self.spreadsheet = None
        self.sheet = None
        self._worksheets_cache = []

        data = self.config_manager.load_json()
        if not isinstance(data, dict):
            self._log("❌ config_manager.load_json() вернул не dict - проверь CONFIG_JSON")
            return

        config_block = data.get("google_config", {})
        defaults = config_block.get("default", {}) or {}
        custom = config_block.get("custom") or {}

        self.creds_file = str(custom.get("creds_file") or defaults.get("creds_file") or "")
        self.sheet_id = str(custom.get("sheet_id") or defaults.get("sheet_id") or "")
        self.auth_sheet_id = str(custom.get("auth_sheet_id") or defaults.get("auth_sheet_id") or "").strip()

        self.worksheet_index = int(custom.get("worksheet_index", defaults.get("worksheet_index", 0)) or 0)
        self.column_index = int(custom.get("column_index", defaults.get("column_index", 0)) or 0)

        self.file_path = str(custom.get("file_path") or defaults.get("file_path") or "").strip()

        client = self._create_client()
        if not client:
            return

        try:
            spreadsheet = client.open_by_key(self.sheet_id)
            self.spreadsheet = spreadsheet
            self._worksheets_cache = spreadsheet.worksheets()
            if not self._worksheets_cache:
                self._log("⚠️ В таблице Google Sheets нет листов")
                self.sheet = None
                return
            # print(self._worksheets_cache)
            # если индекс вдруг вышел за границы
            if 0 <= self.worksheet_index < len(self._worksheets_cache):
                self.sheet = self._worksheets_cache[self.worksheet_index]
            else:
                self._log(f"⚠️ Некорректный worksheet_index={self.worksheet_index}, беру 0")
                self.worksheet_index = 0
                self.sheet = self._worksheets_cache[0]

        except Exception as e:
            self._log(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.spreadsheet = None
            self._worksheets_cache = []
            self.sheet = None

    def open_spreadsheet_by_id(self, sheet_id: str):
        """Открыть любую таблицу по ее ID, используя тот же creds_file."""
        if not sheet_id:
            self._log("❌ Не указан ID таблицы для авторизации.")
            return None

        client = self._create_client()
        if not client:
            return None

        try:
            return client.open_by_key(sheet_id)
        except Exception as e:
            self._log(f"❌ Ошибка открытия таблицы по ID '{sheet_id}': {e}")
            return None

    def list_worksheets(self):
        """Возвращает список листов: [{'title': str, 'index': int}, ...]"""
        try:
            if not getattr(self, "spreadsheet", None):
                self._log("⚠️ spreadsheet не инициализирован")
                return []

            # Используем кэш, если он есть и актуален
            if hasattr(self, '_worksheets_cache') and self._worksheets_cache:
                result = [{"title": ws.title, "index": ws.index} for ws in self._worksheets_cache]
                return result

            # Иначе получаем свежие данные
            result = []
            for ws in self.spreadsheet.worksheets():
                result.append({"title": ws.title, "index": ws.index})

            return result

        except Exception as e:
            self._log(f"⚠️ Не удалось получить список листов: {e}")
            import traceback
            self._log(traceback.format_exc())  # Добавить полный traceback
            return []

    def reconnect(self):
        """Переподключение к Google Sheets"""
        try:
            client = self._create_client()
            if not client:
                return False

            spreadsheet = client.open_by_key(self.sheet_id)
            self.spreadsheet = spreadsheet
            self._worksheets_cache = spreadsheet.worksheets()
            if not self._worksheets_cache:
                self._log("⚠️ В таблице Google Sheets нет листов")
                self.sheet = None
                return False

            if 0 <= self.worksheet_index < len(self._worksheets_cache):
                self.sheet = self._worksheets_cache[self.worksheet_index]
            else:
                self.worksheet_index = 0
                self.sheet = self._worksheets_cache[0]

            return True
        except Exception as e:
            self._log(f"❌ Ошибка переподключения: {e}")
            self.spreadsheet = None
            self._worksheets_cache = []
            self.sheet = None
            return False

    def get_worksheets_list(self):
        """Безопасное получение списка листов"""
        try:
            spreadsheet = getattr(self, "spreadsheet", None)
            if not spreadsheet:
                return []

            # Обновляем кэш
            self._worksheets_cache = spreadsheet.worksheets()

            return [{"title": ws.title, "index": ws.index}
                    for ws in self._worksheets_cache]
        except Exception as e:
            self._log(f"⚠️ Ошибка получения листов: {e}", )
            return []

    def set_active_worksheet(self, index: int):
        """Быстро переключает активный лист, без обращений к Google"""
        try:
            cache = getattr(self, "_worksheets_cache", None)
            if not cache:
                self._log("⚠️ Листы ещё не загружены (нет _worksheets_cache).")
                return

            if not (0 <= index < len(cache)):
                self._log(f"⚠️ Некорректный индекс листа: {index}")
                return

            # просто берем из кэша - локальная операция, без сети
            self.sheet = cache[index]
            self.worksheet_index = index

            # сохраняем выбор в config.custom
            cfg = self.config_manager.load_json() or {}
            gcfg = cfg.setdefault("google_config", {})
            custom = gcfg.setdefault("custom", {})
            custom["worksheet_index"] = index
            self.config_manager.save_in_json(cfg)

            self._log(f"✅ Активный лист: {self.sheet.title}")
        except Exception as e:
            self._log(f"❌ GoogleSheetsManager.set_active_worksheet: {e}")

    @staticmethod
    def _is_completed_status(value) -> bool:
        text = str(value or "").replace("\u00a0", " ").strip()
        text = text.lstrip("= \t\r\n").strip(" \t\r\n\"'")
        normalized = " ".join(text.casefold().split())
        return normalized in {"готов", "готово"}

    def load_data(self):
        """
        Грузим только строки, где:
          1) в колонке M НЕ завершённый статус ('Готов', 'Готово', '= Готово')
          2) хотя бы одна из D/E/F/G/H не пустая.
        При этом тянем только диапазоны D3:H и M3:M, а не весь лист.
        Возвращаем dict: {row_index: [D, E, F, G, H]}.
        """
        try:
            if not self.sheet:
                self._log("⚠️ Лист Google Sheets не инициализирован, пробую переподключиться...")
                if not self.reconnect() or not self.sheet:
                    self._log("⚠️ Лист Google Sheets не инициализирован - пропускаю загрузку")
                    return None

            # Берём 2 диапазона: D3:H и M3:M
            ranges = ["D3:H", "M3:M"]
            values_list = self.sheet.batch_get(ranges, major_dimension="ROWS")
            d_to_h_rows = values_list[0] if len(values_list) > 0 else []
            m_rows = values_list[1] if len(values_list) > 1 else []

            if not d_to_h_rows:
                self._log("⚠️ Таблица пуста или слишком короткая - обновление отменено.")
                return None

            result = {}

            for offset, dh in enumerate(d_to_h_rows):
                # Фактический номер строки в листе (учитываем, что начали с 3-й)
                row_index = 3 + offset

                # Столбец M
                m_val = ""
                if offset < len(m_rows) and m_rows[offset]:
                    m_val = (m_rows[offset][0] or "").strip()

                # Завершённые рейсы не возвращаем как активные: по их отсутствию
                # локальная синхронизация закрывает рейс в таблице.
                if self._is_completed_status(m_val):
                    continue

                # Столбцы D..H
                d = (dh[0] or "").strip() if len(dh) > 0 and dh[0] else ""
                e = (dh[1] or "").strip() if len(dh) > 1 and dh[1] else ""
                f = (dh[2] or "").strip() if len(dh) > 2 and dh[2] else ""
                g = (dh[3] or "").strip() if len(dh) > 3 and dh[3] else ""
                h = (dh[4] or "").strip() if len(dh) > 4 and dh[4] else ""

                # если все D..H пустые - пропускаем
                if not any([d, e, f, g, h]):
                    continue

                # Оставляем только нужное: D..H, привязанные к реальному row_index
                result[row_index] = [d, e, f, g, h]

            if not result:
                self._log("↩️ В листе не найдено подходящих строк (нет активных строк с данными в D–H)")
                return {}

            return result

        except Exception as e:
            self._log(f"️❌ Ошибка загрузки данных с листа: {e}")
            return None
