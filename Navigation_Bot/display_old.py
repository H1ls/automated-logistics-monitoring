def display_data(self):

    self._log_enabled = False
    selected_row = self.table.currentRow()

    try:
        if not self.json_data:
            self.log("JSON пуст после загрузки — отображение отменено.")
            return

        self.table.setRowCount(0)

        for row_idx, row in enumerate(self.json_data):
            self.table.insertRow(row_idx)

            if row.get("id"):
                btn = QPushButton("▶")
                btn.clicked.connect(partial(self._submit_processor_row, row_idx))
            else:
                btn = QPushButton("🛠")
                btn.setStyleSheet("color: red;")
                btn.clicked.connect(partial(self.open_id_editor, row_idx))

            self.table.setCellWidget(row_idx, 0, btn)

            id_value = str(row.get("id", ""))
            container = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(id_value)
            btn_tool = QPushButton("🛠")
            btn_tool.setFixedWidth(30)
            btn_tool.clicked.connect(partial(self.open_id_editor, row_idx))
            layout.addWidget(label)
            layout.addWidget(btn_tool)
            layout.addStretch()
            container.setLayout(layout)
            self.table.setCellWidget(row_idx, 1, container)

            #  ТС + телефон
            ts = row.get("ТС", "")
            phone = row.get("Телефон", "")
            self.set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

            #  КА
            self.set_cell(row_idx, 3, row.get("КА", ""), editable=True)

            # Погрузка / Выгрузка
            self.set_cell(row_idx, 4, self.get_field_with_datetime(row, "Погрузка"))
            self.set_cell(row_idx, 5, self.get_field_with_datetime(row, "Выгрузка"))

            # Гео
            self.set_cell(row_idx, 6, row.get("гео", ""))
            # Время прибытия (col 7)
            arrival = row.get("Маршрут", {}).get("время прибытия", "—")
            arrival_item = QTableWidgetItem(arrival)
            arrival_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row_idx, 7, arrival_item)

            # Запас времени (col 8)
            raw_buffer = row.get("Маршрут", {}).get("time_buffer", "—")

            if ":" in raw_buffer:
                try:
                    h, m = map(int, raw_buffer.split(":"))
                    buffer = f"{h}ч {m}м"
                except Exception:
                    buffer = raw_buffer
            else:
                buffer = raw_buffer

            buffer_item = QTableWidgetItem(buffer)
            buffer_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row_idx, 8, buffer_item)

            arrival_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            buffer_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setWordWrap(True)
        self.table.resizeRowsToContents()

        if selected_row >= 0 and selected_row < self.table.rowCount():
            self.table.selectRow(selected_row)

    except Exception as e:
        self.log(f"Ошибка в display_data(): {e}")

    self._log_enabled = True
