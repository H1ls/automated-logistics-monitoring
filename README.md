# Logistics Management System (Desktop)

Desktop application for transport dispatching and logistics automation. The system integrates Google Sheets, Wialon, PostgreSQL, FastAPI and external automation tools to support dispatchers in their daily workflow.

Проект начался как инструмент для автоматизации ежедневной работы транспортного диспетчера и постепенно вырос в полноценную систему с клиентским приложением, REST API, PostgreSQL и интеграциями с внешними сервисами. Сегодня проект используется в реальном рабочем процессе и продолжает активно развиваться.

## Кратко о проекте

- 🖥 Desktop-приложение на PyQt6
- 🌐 Backend на FastAPI
- 🗄 PostgreSQL
- 🔗 Интеграции: Google Sheets, Wialon, 1C
- 👥 Поддержка ролей пользователей
- 📍 Автоматический расчет маршрутов и ETA
- 🚛 Применяется в реальном рабочем процессе

## О проекте

Система автоматизирует рабочие сценарии транспортного диспетчера: загрузку рейсов, обработку транспорта, расчет маршрутов и ETA, хранение истории, аудит изменений и обмен данными с внешними сервисами.

Основные цели проекта:

- уменьшение количества ручных операций;
- автоматический расчет маршрутов и ETA;
- централизованное хранение данных;
- аудит изменений;
- поддержка нескольких пользователей;
- интеграция с внешними рабочими системами.

Сейчас проект работает в локальном контуре. Серверная версия на FastAPI и PostgreSQL находится в активной разработке и постепенно заменяет старые локальные сценарии.

## Что реализовано в проекте

- **Архитектура:** разделение GUI, прикладного слоя, репозиториев, API и инфраструктурных интеграций.
- **GUI:** desktop-интерфейс на PyQt6 для работы диспетчера с рейсами, транспортом, историей и заметками.
- **Backend API:** REST API на FastAPI для централизованной работы с данными и бизнес-операциями.
- **Database:** PostgreSQL-схема для рейсов, транспорта, маршрутов, истории, заметок, пользователей и audit log.
- **Авторизация:** вход пользователей, временные ключи сессии, роли `admin`, `dispatcher`, `viewer`.
- **Интеграции:** Google Sheets, Wialon, картографические сервисы, LogistX и 1C.
- **Автоматизация:** Selenium- и desktop-сценарии для внешних сервисов и рабочих операций.
- **Надежность данных:** audit log, история изменений, optimistic locking и пакетная запись.
- **Тестирование:** модульные тесты для отдельных сервисов, парсеров и сценариев обработки.

## Архитектура

Ключевая идея архитектуры: GUI не должен напрямую работать с базой данных. Пользовательский интерфейс обращается к API, а серверный слой отвечает за авторизацию, роли, бизнес-операции, аудит и работу с PostgreSQL.

```text
             Google Sheets
               ^     |
               |     v
Wialon <----> PyQt6 GUI <----> FastAPI <----> PostgreSQL
                    ^             |
                    |             v
                  LogistX <----> 1C
```

Основное направление зависимостей:

```text
GUI -> application services -> repositories -> HTTP API
API routes -> PostgreSQL repositories/services -> PostgreSQL
bots/infrastructure -> external systems
```

При запуске пользователь входит по логину и паролю. API выдает временный ключ сессии, который GUI передает в заголовке `X-API-Key`. Для прав доступа используются роли `admin`, `dispatcher` и `viewer`.

Проект разделен по ответственности:

```text
main.py                                      точка входа PyQt6
Navigation_Bot/
  gui/                                      GUI, контроллеры, диалоги, виджеты
  core/
    domain/                                доменные сущности и правила
    application/                           прикладные сценарии
    repositories/                          API- и PostgreSQL-репозитории
    infrastructure/api/                    FastAPI, HTTP-клиент, схемы
    storage/                               PostgreSQL-схема, подключения и pool
  bots/                                    Selenium, Wialon, карты, Google Sheets
LogistX/                                   модуль автоматизации LogistX и 1C
config/                                    локальная конфигурация и runtime-данные
tests/                                     модульные тесты
```

Подробное описание старта GUI вынесено в [docs/gui-startup.md](docs/gui-startup.md).

## Основные возможности

- загрузка и обновление активных рейсов из Google Sheets;
- хранение рейсов, транспорта, маршрутов, навигации, ETA, заметок и событий в PostgreSQL;
- одиночная и пакетная обработка транспорта через Wialon и карты;
- запись результатов навигации обратно в Google Sheets;
- создание и редактирование рейсов из GUI;
- история по рейсу и автомобилю;
- заметки с несколькими вложениями;
- audit log изменений;
- роли пользователей и разграничение доступа;
- локальные страницы реестра PIN-кодов и LogistX;
- импорт отчета и автоматизация закрытия рейса в 1C.

## Поток обработки

Типовой рабочий сценарий:

1. Диспетчер запускает GUI и проходит авторизацию.
2. Приложение загружает активные рейсы из Google Sheets или PostgreSQL.
3. Пользователь выбирает один рейс или пакет рейсов для обработки.
4. Selenium-сценарии получают данные по транспорту из Wialon и картографических сервисов.
5. Прикладной слой рассчитывает маршрутные данные, ETA и статус обработки.
6. Результаты сохраняются в PostgreSQL и, при необходимости, записываются обратно в Google Sheets.
7. Все значимые изменения фиксируются в audit log.
8. Для отдельных процессов используется модуль LogistX и автоматизация 1C.

## Технологии

| Категория | Технологии |
|---|---|
| Language | Python 3.11+ |
| Desktop | PyQt6 |
| Backend | FastAPI, Uvicorn |
| Database | PostgreSQL, psycopg 3, psycopg_pool |
| Integrations | Google Sheets API, Wialon, 1C |
| Automation | Selenium, PyAutoGUI, pywin32 |
| OCR | Tesseract, pytesseract |
| Data processing | openpyxl, requests |
| Testing | pytest, unittest |

## Требования и установка

- Windows;
- Python 3.11+;
- PostgreSQL;
- браузер и совместимый WebDriver;
- для LogistX: доступ к RDP/1C, при использовании OCR - Tesseract.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Конфигурация

Приложение читает переменные окружения и корневой `.env`. Уже существующие переменные окружения имеют приоритет.

Минимальный `.env`:

```dotenv
POSTGRES_DSN=postgresql://user:password@localhost:5432/logistics
NAV_API_BASE_URL=http://127.0.0.1:8000
GOOGLE_CREDENTIALS_PATH=D:\secrets\google-service-account.json
WIALON_USERNAME=user
WIALON_PASSWORD=password
```

Дополнительные параметры описаны в [docs/configuration.md](docs/configuration.md).

Секреты, cookies и рабочие конфигурации не должны попадать в Git.

## Запуск

Сначала запускается API из корня проекта:

```powershell
.\.venv\Scripts\uvicorn.exe Navigation_Bot.core.infrastructure.api.main:app `
  --host 127.0.0.1 `
  --port 8000
```

API применяет `Navigation_Bot/core/storage/postgres_schema.sql`, открывает pool подключений и публикует:

- Swagger: `http://127.0.0.1:8000/docs`;
- ReDoc: `http://127.0.0.1:8000/redoc`;
- API: `http://127.0.0.1:8000/api/v1`.

Затем в другом PowerShell запускается GUI:

```powershell
$env:NAV_API_BASE_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe main.py
```

Если в БД еще нет активных пользователей с паролем, первая успешная попытка входа создает пользователя с ролью `admin`. Дальше пользователей создает администратор через GUI или API.

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

## Roadmap

- расширить покрытие тестами для API и прикладных сервисов;
- добавить миграции БД вместо применения единого SQL-файла;
- улучшить наблюдаемость: структурные логи, health-checks, метрики;
- подготовить Docker Compose для локального запуска API и PostgreSQL;
- доработать управление пользователями и ролями;
- формализовать сценарии восстановления после ошибок внешних сервисов.

## Документация

- [API](Navigation_Bot/core/infrastructure/api/README.md)
- [Конфигурация](docs/configuration.md)
- [Старт GUI](docs/gui-startup.md)
- [Google Sheets -> PostgreSQL](docs/google_sheets_tabs_to_db.md)
- [Фильтры задач и UI-меню](docs/task_filters_and_ui_menus.md)
- [Расчет ETA через карты](docs/yandex_maps_eta.md)
