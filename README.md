# Navigation Manager

Desktop-приложение для диспетчеров, которые ведут рейсы, машины и навигацию в одном окне.

Текущая рабочая схема хранения:

```text
GUI -> FastAPI -> PostgreSQL
```

GUI больше не подключается к базе напрямую. Все рабочие данные идут через API, а PostgreSQL хранит рейсы, ТС, водителей, перевозчиков, точки маршрута, историю навигации, ETA, заметки, пользователей, роли и audit log.

## Возможности

- Загрузка активных рейсов из Google Sheets и разделение данных по листам.
- Сохранение рейсов и справочника ТС в PostgreSQL.
- Обработка одной строки или пакетный прогон ТС через Wialon и карты.
- Сбор навигационных данных: адрес/геозона, координаты, скорость, свежесть GPS.
- Расчет расстояния, ETA и запаса времени до выгрузки.
- Запись результатов обработки обратно в Google Sheets.
- Создание и редактирование рейсов из GUI.
- Редактирование ID мониторинга, адресов, заметок и отдельных полей рейса.
- История навигации по рейсу и по ТС.
- Audit log: кто и что поменял.
- Роли пользователей: `admin`, `dispatcher`, `viewer`.
- Локальные вкладки: реестр PIN-кодов и LogistX.

## Архитектура

```text
main.py
Navigation_Bot/
  api/                  FastAPI API для GUI и внешних клиентов
  gui/                  PyQt6-интерфейс, контроллеры, диалоги, таблицы
  core/                 доменная модель, сервисы, PostgreSQL/API repositories, настройки
  bots/                 Selenium/WebDriver, Wialon, карты, Google Sheets
LogistX/
  gui/                  локальная страница LogistX
  onec/                 сценарии автоматизации 1C
  controllers/          импорт отчетов и вспомогательные контроллеры
config/                 локальные настройки, cookies, медиа и служебные файлы
```

Ключевые слои:

- `Navigation_Bot.api` - HTTP API, роли, API-ключи, audit log, доступ к PostgreSQL.
- `Navigation_Bot.gui` - рабочее окно приложения и пользовательские сценарии.
- `Navigation_Bot.core.application.services` - бизнес-сервисы задач, Google-синхронизации, истории и редактирования.
- `Navigation_Bot.core.repositories` - API/PostgreSQL репозитории.
- `Navigation_Bot.core.NavigationProcessor` - обработка строк, браузерная сессия, Wialon/карты и пакетный прогон.
- `LogistX.onec` - шаги закрытия рейса в 1C.

## Данные и конфигурация

Основные локальные файлы:

- `config/config.json` - настройки Google Sheets, селекторы Wialon/карт и параметры приложения.
- `config/Credentials_wialon.json` - учетные данные Wialon, если используются текущими сценариями.
- `config/cookies.pkl` - cookies браузерной сессии.
- `config/ui_settings.json` - размеры окна, таблицы и UI-настройки.
- `config/media/notes/` - медиафайлы заметок.
- `LogistX/config/logistx_sample.json` - локальные данные LogistX.
- `LogistX/config/sites_db.json` - база соответствий адресов и геозон.

Секреты, реальные credentials и API tokens не нужно коммитить в репозиторий.

## Установка

Требуется Windows, Python 3.11+, PostgreSQL и браузер/драйвер, совместимый с Selenium.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Для OCR/LogistX-сценариев может понадобиться Tesseract и доступ к RDP/1C-окну.

## Запуск API

```powershell
.venv\Scripts\uvicorn.exe Navigation_Bot.api.main:app --host 127.0.0.1 --port 8000
```

Полная документация API: [Navigation_Bot/api/README.md](Navigation_Bot/api/README.md)

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health:

```text
http://127.0.0.1:8000/api/v1/health
```

## Запуск GUI

В отдельном PowerShell после запуска API:

```powershell
$env:DB_BACKEND = "api"
$env:NAV_API_BASE_URL = "http://127.0.0.1:8000"
$env:NAV_API_KEY = "nav_..."
.venv\Scripts\python.exe main.py
```

`NAV_API_KEY` - API token пользователя. GUI отправляет его в API как заголовок `X-API-Key`.

При старте GUI пишет текущего пользователя в лог:

```text
API user: dispatcher1 (dispatcher)
```

## PostgreSQL

Подключение задается через `POSTGRES_DSN`.

Пример:

```powershell
$env:POSTGRES_DSN = "postgresql://pet_user:postgres@localhost:5432/pet_project"
```

API использует connection pool. Для локального режима и 30-50 пользователей можно начать с:

```powershell
$env:POSTGRES_POOL_MIN_SIZE = "2"
$env:POSTGRES_POOL_MAX_SIZE = "10"
$env:POSTGRES_POOL_TIMEOUT = "10"
```

## Пользователи

Роли:

- `admin` - пользователи, API-ключи, чтение/запись всех данных, audit log.
- `dispatcher` - чтение/запись рейсов, машин, заметок, навигации и истории.
- `viewer` - только чтение.

API token создается через:

```text
POST /api/v1/users/{user_id}/api-keys
```

Отзыв ключа:

```text
POST /api/v1/api-keys/{key_id}/revoke
```

## Работа с Google Sheets

Менеджер Google Sheets читает настройки из `config/config.json`.

Используется service account. Файл credentials должен содержать блок `credentials`, из которого создается клиент `gspread`. Таблица должна быть доступна сервисному аккаунту.

Загрузка берет рабочие диапазоны из листа, пропускает завершенные строки и сохраняет результат через FastAPI в PostgreSQL. Обработка строки обновляет состояние через API и пишет результаты обратно в Google Sheets через сервис записи.

## Работа с Wialon и картами

Selenium-сессия создается лениво при первом открытии Wialon или обработке строки. Селекторы Wialon и карт настраиваются в GUI:

- поиск ТС;
- блок ТС;
- адрес, геозона, координаты, скорость и GPS-индикаторы;
- построение маршрута, длительность и расстояние.

При изменении селекторов приложение сбрасывает внутренние bot-объекты, чтобы следующие операции шли с обновленными настройками.

## LogistX

Вкладка LogistX предназначена для отдельного процесса закрытия рейсов:

- импорт отчета из 1C через RDP;
- отображение ТС, номера рейса, отправления, назначения и плановой даты;
- сопоставление адресов с геозонами из `sites_db.json`;
- ручное редактирование базы адресов;
- запуск сценария закрытия рейса кнопкой в строке;
- сохранение результата обратно в локальный JSON.

## Технологии

- Python
- PyQt6
- FastAPI
- PostgreSQL
- psycopg / psycopg_pool
- Selenium
- gspread / Google Sheets API
- PyAutoGUI / PyDirectInput / pywin32
- OpenCV / Pillow / pytesseract
- openpyxl
- PyInstaller

## Статус

Основное направление сейчас - стабилизация многопользовательского режима через FastAPI/PostgreSQL, очистка старого legacy-слоя и дальнейшая оптимизация API-запросов под 30-50 пользователей.
