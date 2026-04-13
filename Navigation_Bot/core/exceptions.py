
class NavigationBotError(Exception):
    """Базовое исключение для Navigation Bot"""
    pass

class DataContextError(NavigationBotError):
    """Ошибка при работе с контекстом данных"""
    pass

class FileOperationError(DataContextError):
    """Ошибка при работе с файлом"""
    pass

class JSONFormatError(DataContextError):
    """Ошибка при парсинге JSON"""
    pass

class JSONValidationError(JSONFormatError):
    """Ошибка валидации JSON структуры"""
    pass

class WialonConnectionError(NavigationBotError):
    """Ошибка подключения к Wialon"""
    pass

class WialonAuthError(WialonConnectionError):
    """Ошибка авторизации в Wialon"""
    pass

# === Browser/Selenium exceptions ===

class BrowserError(NavigationBotError):
    """Базовая ошибка браузера"""
    pass

class BrowserTimeoutError(BrowserError):
    """Таймаут при ожидании элемента в браузере"""
    pass

class ElementNotFoundError(BrowserError):
    """Элемент не найден на странице"""
    pass

class PageLoadError(BrowserError):
    """Ошибка загрузки страницы"""
    pass

# === Google Sheets exceptions ===

class GoogleSheetsError(NavigationBotError):
    """Ошибка при работе с Google Sheets"""
    pass

class GoogleAuthError(GoogleSheetsError):
    """Ошибка авторизации Google"""
    pass

class SheetOperationError(GoogleSheetsError):
    """Ошибка операции с листом"""
    pass