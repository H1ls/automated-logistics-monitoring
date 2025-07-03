# 📋 TODO / Дорожная карта проекта

Это список текущих улучшений, задач и рекомендаций по проекту **Navigation_Bot**.

---

## ✅ Готово

- [x] Вынесена логика таблицы в TableManager
- [x] Создан NavigationProcessor
- [x] Настроено логирование через `log_func`
- [x] Используется JSONManager для конфигурации

---

## 🔧 В процессе

- [ ] Вынести логирование в `AppLogger` с уровнями (user, mod, admin)
- [ ] Добавить DataModel (например, `CarEntry`) как прослойку над `json_data`
- [ ] Вынести работу с селекторами в `SelectorManager`
- [ ] Переписать `process_row_wrapper` и `process_navigation_from_json` на подметоды
- [ ] Добавить валидацию ID и формата координат перед сохранением
- [ ] Реализовать `LoggerManager` с фильтрацией логов по GUI-флажку

---

## 💡 Предложения на будущее

- [ ] Юнит-тесты для: `dataCleaner`, `navigationProcessor`, `jSONManager`
- [ ] Фильтрация таблицы по ТС
- [ ] Кнопка "🛠" только при отсутствии ID
- [ ] Экспорт в Excel
- [ ] API вместо Selenium для Wialon
- [ ] Поддержка дообучения ML-модели на пользовательских правках

---

## 📁 Предлагаемая структура проекта

```
Navigation_Bot/
├── bots/
│   ├── navigationBot.py
│   ├── mapsBot.py
│   ├── dataCleaner.py
│   └── driverManager.py
├── core/
│   ├── jsonManager.py
│   ├── selectorManager.py
│   ├── dataModel.py
│   └── loggerManager.py
├── gui/
│   ├── Gui.py
│   ├── tableManager.py
│   ├── trackingIdEditor.py
│   ├── settingsDialogManager.py
│   └── genericSettingsDialog.py
├── config/
│   ├── config.json
│   └── Id_car.json
```

---
