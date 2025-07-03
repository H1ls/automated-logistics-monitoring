# 🛠 Project Audit & TODO List (Developer Notes)

This document summarizes the current state of the Navigation_Bot project after a full code audit.
It includes architecture strengths, improvement areas, and concrete TODO tasks.

---

## ✅ Architecture Strengths

- Clear separation of concerns (GUI, Data, Processing, Parsing)
- Modular structure (TableManager, NavigationProcessor, WebDriverManager)
- Centralized JSON handling via JSONManager
- Selenium logic cleanly encapsulated (mapsBot, navigationBot)
- Good UX ideas in GUI: status buttons (🛠 ▶), Wialon/Yandex switching
- Future-ready: prepared for multi-level logging and DataModel integration

---

## 🔧 Priority Improvements

### 🔴 High Priority

- [ ] **Introduce `DataModel` layer**
    - Create `CarEntry` class to wrap JSON row
    - Refactor: TableManager, NavigationProcessor, TrackingIdEditor to use it
    - Benefit: validation, structured access, testability

- [ ] **Split `process_row_wrapper()` into smaller methods**
    - Improves testability and readability

### 🟠 Medium Priority

- [ ] **Implement `LoggerManager`**
    - Levels: USER, EXTENDED, MODERATOR, ADMIN
    - Filter log messages based on selected level
    - Replace all `.log()` with structured logger

- [ ] **Create `SelectorManager`**
    - Unify selector access for `wialon`, `yandex`
    - Remove hardcoded keys in SettingsDialogManager and bots

- [ ] **Extract ID logic into `IdManager`**
    - Separate check, assign, and store logic for `Id_car.json`

### 🟡 Low Priority

- [ ] **Enhance `GenericSettingsDialog`**
    - Add reset-to-default button
    - Support field validation (required fields)
    - Accept external `log_func`

- [ ] **Improve UI features**
    - Disable ▶ if no coordinates
    - Only show 🛠 if ID is missing
    - Add `QMessageBox` with “Don't ask again” checkbox

---

## ✨ Future Features

- [ ] Quick filter by TС (search bar)
- [ ] Export JSON → Excel with formatting
- [ ] Migrate Wialon from Selenium → API
- [ ] ML-powered address parsing + UI feedback for fine-tuning
- [ ] Auto-saving dirty rows after inactivity

---

## 🧪 Recommended Unit Tests

- [ ] `dataCleaner._parse_info()`
- [ ] `JSONManager.save/load/update_json()`
- [ ] `NavigationProcessor.process_row_wrapper()` (mocked)
- [ ] `TableManager._save_item()` logic for ТС/Телефон

---

_Last updated: Project audit, June 2025_