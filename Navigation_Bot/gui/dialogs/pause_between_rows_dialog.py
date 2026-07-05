"""
Диалог паузы между обработкой строк в batch режиме.
Показывает таймер и позволяет остановить обработку или продолжить.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import QTimer, Qt, QRect

from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog


class PauseBetweenRowsDialog(BaseDialog):
    """
    Модальный диалог, который появляется между обработкой ТС.
    Показывает:
    - Информацию о текущей ТС и номере обработки
    - Отсчёт таймера
    - Кнопки "Продолжить" и "Стоп"
    
    Результаты:
    - Accepted: продолжить на следующую ТС
    - Rejected: остановить batch обработку
    """

    def __init__(self, current_row_idx: int,
                 current_row_info: str,
                 processed_count: int,
                 total_count: int,
                 timeout_seconds: int = 3,
                 parent=None):
        """
        Args:
            current_row_idx: индекс текущей обрабатываемой ТС
            current_row_info: описание текущей ТС (например "К532СМ - Петров")
            processed_count: количество уже обработанных ТС
            total_count: всего ТС для обработки
            timeout_seconds: сколько секунд длится таймер
            parent: родительское окно
        """
        super().__init__(title="Пауза между обработкой ТС", size=(500, 250), parent=parent)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Отцентрируем относительно родительского окна
        if parent:
            self._center_on_parent(parent)

        self.current_row_idx = current_row_idx
        self.current_row_info = current_row_info
        self.processed_count = processed_count
        self.total_count = total_count
        self.timeout_seconds = timeout_seconds
        self.remaining_seconds = timeout_seconds
        self.user_clicked_continue = False
        self.cancelled = False
        self._init_ui()
        self._start_timer()

    def _init_ui(self):
        """Построить интерфейс диалога"""
        self.root.setSpacing(15)
        self.root.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        title = QLabel("✅ Обработка ТС завершена")
        title_font = title.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        self.root.addWidget(title)

        # Информация о ТС
        info_text = f"ТС: {self.current_row_info}"
        info_label = QLabel(info_text)
        info_font = info_label.font()
        info_font.setPointSize(11)
        info_label.setFont(info_font)
        self.root.addWidget(info_label)

        # Статус прогресса
        progress_text = f"Обработано: {self.processed_count} из {self.total_count}"
        progress_label = QLabel(progress_text)
        self.root.addWidget(progress_label)

        # Таймер
        self.root.addSpacing(10)
        timer_label = QLabel()
        timer_font = timer_label.font()
        timer_font.setPointSize(16)
        timer_font.setBold(True)
        timer_label.setFont(timer_font)
        timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label = timer_label
        self.root.addWidget(timer_label)

        # Описание
        desc = QLabel("Обработка будет продолжена автоматически через таймер\n"
                      "Нажмите «Стоп» чтобы прервать обработку" )

        desc.setStyleSheet("color: #666; font-size: 10px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root.addWidget(desc)

        self.root.addStretch()

        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.btn_continue = QPushButton("▶ Продолжить")
        self.btn_stop = QPushButton("⏹ Стоп")
        self.btn_cancel = QPushButton("⏹ Отмена")

        self.btn_continue.setMinimumWidth(120)
        self.btn_stop.setMinimumWidth(120)
        self.btn_cancel.setMinimumWidth(120)

        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_continue.clicked.connect(self._on_continue_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)

        button_layout.addWidget(self.btn_continue)
        button_layout.addWidget(self.btn_stop)
        button_layout.addStretch()

        self.root.addLayout(button_layout)

        # Инициализируем отображение таймера
        self._update_timer_display()

    def _on_cancel(self):
        self.cancelled = True
        self.reject()

    def _start_timer(self):
        """Запустить QTimer для отсчёта"""
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start(1000)  # обновляем каждую секунду

    def _on_timer_tick(self):
        """Обновить таймер и автоматически продолжить если время вышло"""
        self.remaining_seconds -= 1
        self._update_timer_display()

        if self.remaining_seconds <= 0:
            self.timer.stop()
            # Таймер вышел - автоматически закрываемся с accept
            self.user_clicked_continue = True
            self.accept()

    def _update_timer_display(self):
        """Обновить отображение оставшегося времени"""
        self.timer_label.setText(f"⏱ {self.remaining_seconds:02d} сек")

        # Меняем цвет по мере приближения конца
        if self.remaining_seconds > 5:
            self.timer_label.setStyleSheet("color: #2196F3;")  # синий
        elif self.remaining_seconds > 2:
            self.timer_label.setStyleSheet("color: #FF9800;")  # оранжевый
        else:
            self.timer_label.setStyleSheet("color: #F44336;")  # красный

    def _on_continue_clicked(self):
        """Пользователь нажал 'Продолжить'"""
        self.timer.stop()
        self.user_clicked_continue = True
        self.accept()

    def _on_stop_clicked(self):
        """Пользователь нажал 'Стоп'"""
        self.timer.stop()
        self.user_clicked_continue = False
        self.reject()

    def closeEvent(self, event):
        """Убедиться что таймер остановлен при закрытии"""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)

    def was_stopped_by_user(self) -> bool:
        """Был ли диалог закрыт кнопкой 'Стоп' (не таймер)"""
        return not self.user_clicked_continue and self.result() == QDialog.DialogCode.Rejected

    def _center_on_parent(self, parent):
        """Отцентрировать диалог относительно родительского окна"""
        if not parent:
            return

        try:
            # Получаем геометрию родительского окна
            parent_rect = parent.geometry()
            parent_center_x = parent_rect.x() + parent_rect.width() // 2
            parent_center_y = parent_rect.y() + parent_rect.height() // 2

            # Позиционируем диалог в центре
            dialog_x = parent_center_x - self.width() // 2
            dialog_y = parent_center_y - self.height() // 2

            self.move(dialog_x, dialog_y)
        except Exception:
            # Если что-то не так - пусть окна система сама расположит
            pass
