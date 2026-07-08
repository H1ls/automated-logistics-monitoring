# Конфигурация

Приложение читает переменные окружения и корневой `.env`. Уже существующие переменные окружения имеют приоритет над значениями из файла.

## Минимальный `.env`

```dotenv
POSTGRES_DSN=postgresql://user:password@localhost:5432/logistics
NAV_API_BASE_URL=http://127.0.0.1:8000
GOOGLE_CREDENTIALS_PATH=D:\secrets\google-service-account.json
WIALON_USERNAME=user
WIALON_PASSWORD=password
```

## Дополнительные параметры

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `POSTGRES_POOL_MIN_SIZE` | `2` | Минимальный размер pool API |
| `POSTGRES_POOL_MAX_SIZE` | `10` | Максимальный размер pool API |
| `POSTGRES_POOL_TIMEOUT` | `10` | Ожидание подключения, секунд |
| `NAV_GUI_SESSION_HOURS` | `12` | Срок ключа GUI-сессии |
| `NAV_API_TASK_PAGE_SIZE` | `500` | Размер страницы при полной загрузке GUI |
| `NAV_API_INCREMENTAL_REFRESH` | выключен | Инкрементальное обновление списка рейсов |
| `NAV_GUI_SKIP_LOGIN` | выключен | Пропуск формы входа для отладки |
| `NAV_API_KEY` | - | Постоянный API-ключ или аварийный env-admin ключ |

## Локальные файлы

- `config/config.json` - Google Sheets, селекторы и параметры обработки;
- `config/cookies.pkl` - cookies браузерной сессии;
- `config/ui_settings.json` - состояние окна и таблиц;
- `config/media/notes/` - вложения заметок, вставленные из буфера обмена;
- `LogistX/config/sites_db.json` - адреса, aliases и геозоны;
- `LogistX/config/onec_ui_map_v2.json` - карта элементов интерфейса 1C.

Секреты, cookies и рабочие конфигурации не должны попадать в Git.
