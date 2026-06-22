from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Navigation_Bot.bots.google_sheets_manager import GoogleSheetsManager
    from Navigation_Bot.core.application.services.editable_field_workflow_service import EditableFieldWorkflowService
    from Navigation_Bot.core.application.services.google.google_account_auth_service import GoogleAccountAuthService
    from Navigation_Bot.core.application.services.google.google_navigation_writer import GoogleNavigationWriter
    from Navigation_Bot.core.application.services.google.google_sync_service import GoogleSyncService
    from Navigation_Bot.core.application.services.navigation.navigation_processor import NavigationProcessor
    from Navigation_Bot.core.application.services.new_task_workflow_service import NewTaskWorkflowService
    from Navigation_Bot.core.application.services.task_edit_service import TaskEditService
    from Navigation_Bot.core.application.services.tasks_service import TasksService
    from Navigation_Bot.core.infrastructure.api.api_client import NavigationApiClient
    from Navigation_Bot.core.repositories.api_task_repository import ApiTaskRepository
    from Navigation_Bot.core.repositories.api_vehicle_repository import ApiVehicleRepository
    from Navigation_Bot.core.settings.settings_controller import SettingsController
    from Navigation_Bot.gui.app.address_edit_workflow_service import AddressEditWorkflowService
    from Navigation_Bot.gui.controllers.table_context_menu_controller import TableContextMenuController
    from Navigation_Bot.gui.controllers.task_table_controller import TaskTableController
    from Navigation_Bot.gui.dialogs.combined_settings_dialog import CombinedSettingsDialog
    from Navigation_Bot.gui.services.hotkey_manager import HotkeyManager
    from Navigation_Bot.gui.settings.ui_bridge import UiBridge
    from Navigation_Bot.gui.widgets.row_high_lighter import RowHighlighter
    from Navigation_Bot.gui.widgets.table.table_manager import TableManager
    from Navigation_Bot.gui.widgets.table_sort_controller import TableSortController
    from Navigation_Bot.core.application.services.api_history_services import (ApiNavigationHistoryService,
                                                                               ApiNoteHistoryService,
                                                                               ApiRouteEstimateHistoryService,
                                                                               ApiStatusEventService,
                                                                               )

@dataclass(slots=True)
class AppContext:
    """Зависимости времени выполнения, принадлежащие приложению, а не главному окну."""

    api_client: NavigationApiClient = field(init=False)
    vehicle_repository: ApiVehicleRepository = field(init=False)
    task_repository: ApiTaskRepository = field(init=False)
    gsheet: GoogleSheetsManager = field(init=False)
    google_navigation_writer: GoogleNavigationWriter = field(init=False)
    google_account_auth_service: GoogleAccountAuthService = field(init=False)
    tasks_service: TasksService = field(init=False)
    task_edit_service: TaskEditService = field(init=False)
    google_sync_service: GoogleSyncService = field(init=False)
    status_event_service: ApiStatusEventService = field(init=False)
    navigation_history_service: ApiNavigationHistoryService = field(init=False)
    route_estimate_history_service: ApiRouteEstimateHistoryService = field(init=False)
    note_history_service: ApiNoteHistoryService = field(init=False)
    new_task_workflow_service: NewTaskWorkflowService = field(init=False)
    editable_field_workflow_service: EditableFieldWorkflowService = field(init=False)
    address_edit_workflow_service: AddressEditWorkflowService = field(init=False)
    settings_controller: SettingsController = field(init=False)
    settings_ui: CombinedSettingsDialog = field(init=False)
    table_manager: TableManager = field(init=False)
    task_table_controller: TaskTableController = field(init=False)
    row_highlighter: RowHighlighter = field(init=False)
    processor: NavigationProcessor = field(init=False)
    sort_controller: TableSortController = field(init=False)
    hotkeys: HotkeyManager = field(init=False)
    table_context_menu: TableContextMenuController = field(init=False)
    ui_bridge: UiBridge = field(init=False)
