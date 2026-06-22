# Navigation Manager

Windows-приложение для диспетчеров: ведение рейсов и транспорта, синхронизация с Google Sheets, сбор навигационных данных через Wialon и карты, расчёт ETA и автоматизация закрытия рейсов в 1С.

```Ждем сервер для переезда с local```

## Архитектура

Рабочие данные проходят через единый серверный контур:

```text
PyQt6 GUI ──HTTP/X-API-Key──> FastAPI ──connection pool──> PostgreSQL
    │                              │
    ├── Google Sheets              ├── аутентификация и роли
    ├── Selenium: Wialon/карты     ├── audit log
    └── LogistX: RDP/1С            └── optimistic locking и batch-запись
```

GUI не подключается к PostgreSQL напрямую. При запуске пользователь входит по логину и паролю; API выдаёт временный ключ сессии, который GUI передаёт в заголовке `X-API-Key`.

Проект разделён по ответственности:

```text
main.py                                      точка входа PyQt6
Navigation_Bot/
  gui/
    app/                                     composition root и контекст GUI
    builders/, controllers/                  сборка интерфейса и сценарии UI
    dialogs/, widgets/, main_window/         представление
    services/, settings/                     UI-сервисы и локальные настройки
  core/
    domain/                                  сущности, value objects и доменные правила
    application/
      services/                              прикладные сценарии
      services/google/                       синхронизация с Google Sheets
      services/navigation/                   обработка строки и пакетная навигация
      mappers/                               преобразование внешних данных
    repositories/                            API- и PostgreSQL-репозитории
    infrastructure/
      api/                                   FastAPI, HTTP-клиент, схемы и smoke-тесты
      persistence/                           файловые адаптеры
    storage/                                 PostgreSQL-схема, подключения и pool
    settings/                                настройки приложения
  bots/                                      Selenium, Wialon, карты и Google Sheets
LogistX/
  gui/, services/                            локальная страница LogistX
  onec/                                      сценарии и шаги автоматизации 1С
  controllers/, runner/                      импорт отчётов и отдельный запуск
config/                                      локальная конфигурация и runtime-данные
tests/                                       модульные тесты
```

Направление зависимостей для основного сценария:

```text
GUI -> application services -> repositories -> HTTP API
API routes -> PostgreSQL repositories/services -> PostgreSQL
bots/infrastructure -> внешние системы
```

`Navigation_Bot.gui.app.AppServices` — composition root GUI: создаёт API-клиент и репозитории, прикладные сервисы, процессор навигации и UI-контроллеры. FastAPI собирает серверные зависимости в `core.infrastructure.api`.

## Основные возможности

- загрузка и обновление активных рейсов из Google Sheets;
- хранение рейсов, транспорта, маршрутов, навигации, ETA, заметок и событий в PostgreSQL;
- одиночная и пакетная обработка транспорта через Wialon и карты;
- запись результатов навигации обратно в Google Sheets;
- создание и редактирование рейсов из GUI;
- история по рейсу и автомобилю, audit log изменений;
- роли `admin`, `dispatcher`, `viewer`;
- локальные страницы реестра PIN-кодов и LogistX;
- импорт отчёта и автоматизация закрытия рейса в 1С.

## Требования и установка

- Windows;
- Python 3.11+;
- PostgreSQL;
- браузер и совместимый WebDriver;
- для LogistX: доступ к RDP/1С, при использовании OCR — Tesseract.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Конфигурация

Приложение читает переменные окружения и корневой `.env` (существующие переменные окружения имеют приоритет).

Минимальный `.env`:

```dotenv
POSTGRES_DSN=postgresql://pet_user:pet_password@localhost:5432/pet_project
NAV_API_BASE_URL=http://127.0.0.1:8000
GOOGLE_CREDENTIALS_PATH=D:\secrets\google-service-account.json
WIALON_USERNAME=user
WIALON_PASSWORD=password
```

Дополнительные параметры:

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `POSTGRES_POOL_MIN_SIZE` | `2` | Минимальный размер pool API |
| `POSTGRES_POOL_MAX_SIZE` | `10` | Максимальный размер pool API |
| `POSTGRES_POOL_TIMEOUT` | `10` | Ожидание подключения, секунд |
| `NAV_GUI_SESSION_HOURS` | `12` | Срок ключа GUI-сессии, 1–168 часов |
| `NAV_API_TASK_PAGE_SIZE` | `500` | Размер страницы при полной загрузке GUI |
| `NAV_API_INCREMENTAL_REFRESH` | выключен | Инкрементальное обновление списка рейсов |
| `NAV_GUI_SKIP_LOGIN` | выключен | Пропустить форму входа и взять `NAV_API_KEY`; только для отладки |
| `NAV_API_KEY` | — | Постоянный API-ключ или аварийный env-admin ключ |

Локальные файлы:

- `config/config.json` — Google Sheets, селекторы и параметры обработки;
- `config/cookies.pkl` — cookies браузерной сессии;
- `config/ui_settings.json` — состояние окна и таблиц;
- `config/media/notes/` — вложения заметок;
- `LogistX/config/sites_db.json` — адреса, aliases и геозоны;
- `LogistX/config/onec_ui_map_v2.json` — карта элементов интерфейса 1С.

Секреты, cookies и рабочие конфигурации не должны попадать в Git.

## Запуск

Сначала запустите API из корня проекта:

```powershell
.\.venv\Scripts\uvicorn.exe Navigation_Bot.core.infrastructure.api.main:app `
  --host 127.0.0.1 `
  --port 8000
```

При старте API применяет `Navigation_Bot/core/storage/postgres_schema.sql`, открывает pool и публикует:

- Swagger: `http://127.0.0.1:8000/docs`;
- ReDoc: `http://127.0.0.1:8000/redoc`;
- API: `http://127.0.0.1:8000/api/v1`.

Затем в другом PowerShell запустите GUI:

```powershell
$env:NAV_API_BASE_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe main.py
```

Если в БД ещё нет активных пользователей с паролем, первая успешная попытка входа создаёт пользователя с ролью `admin`. Дальше пользователей создаёт администратор через диалог GUI или API.

Подробные endpoint-ы, модель доступа и нагрузочные проверки описаны в [документации API](Navigation_Bot/core/infrastructure/api/README.md).

## Проверки

Модульные тесты:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Проверка регистрации маршрутов без запуска сервера:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.check_api
```

Smoke- и нагрузочные команды приведены в документации API.
