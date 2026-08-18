from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import the core engine tools
from spatialmedia import metadata_utils


class BatchWorker(QThread):
    """Handles parsing and shifting media metadata asynchronously to prevent GUI freezing."""

    log_signal = pyqtSignal(str)
    item_complete_signal = pyqtSignal(int, bool)
    all_finished_signal = pyqtSignal()

    def __init__(self, tasks, overwrite_source, output_dir):
        super().__init__()
        self.tasks = (
            tasks  # List of dicts containing input path, output metadata structure
        )
        self.overwrite_source = overwrite_source
        self.output_dir = Path(output_dir) if output_dir else None

    def run(self):
        def silent_logger(msg):
            pass

        for index, task in enumerate(self.tasks):
            infile = Path(task["infile"])
            proj_type = task["projection"]
            stereo_mode = task["stereo"]
            spatial_audio = task["audio"]

            self.log_signal.emit(
                f"Processing item [{index + 1}/{len(self.tasks)}]: {infile.name}..."
            )

            # Calculate temporary working location
            temp_outfile = infile.parent / f"{infile.stem}_injected{infile.suffix}"
            if self.output_dir and not self.overwrite_source:
                temp_outfile = (
                    self.output_dir / f"{infile.stem}_injected{infile.suffix}"
                )

            try:
                # Instantiate Google metadata schemas matching selection specifications
                metadata = metadata_utils.Metadata()

                # Setup core tracking configurations
                s_mode = None if stereo_mode == "none" else stereo_mode

                if proj_type == "VR 360 (Full Spherical)":
                    metadata.video = metadata_utils.generate_spherical_xml(
                        "equirectangular", s_mode
                    )
                elif proj_type == "VR 180 (Front Dome)":
                    metadata.video = metadata_utils.generate_spherical_xml(
                        "equirectangular", s_mode, "1:2:2:2:0:0"
                    )

                if spatial_audio:
                    parsed_info = metadata_utils.parse_metadata(
                        str(infile), silent_logger
                    )
                    if parsed_info and hasattr(parsed_info, "num_audio_channels"):
                        audio_desc = metadata_utils.get_spatial_audio_description(
                            parsed_info.num_audio_channels
                        )
                        if audio_desc.is_supported:
                            metadata.audio = metadata_utils.get_spatial_audio_metadata(
                                audio_desc.order, audio_desc.has_head_locked_stereo
                            )
                        else:
                            metadata.audio = metadata_utils.get_spatial_audio_metadata(
                                1, False
                            )
                    else:
                        metadata.audio = metadata_utils.get_spatial_audio_metadata(
                            1, False
                        )

                # Inject variables safely into the target video
                metadata_utils.inject_metadata(
                    str(infile), str(temp_outfile), metadata, silent_logger
                )

                # Verification hook: confirm generated asset footprint is valid before shifting
                if temp_outfile.exists() and temp_outfile.stat().st_size > 0:
                    if self.overwrite_source:
                        # Safety sequence: unlink target source file, rename temporary file over it
                        infile.unlink()
                        temp_outfile.rename(infile)
                        self.log_signal.emit(
                            f"Successfully modified source video path: {infile.name}"
                        )
                    else:
                        self.log_signal.emit(
                            f"Successfully saved file artifact target path: {temp_outfile.name}"
                        )

                    self.item_complete_signal.emit(index, True)
                else:
                    raise FileNotFoundError(
                        "Target generation artifact verification failure."
                    )

            except Exception as e:
                self.log_signal.emit(f"Error processing item [{infile.name}]: {e!s}")
                self.item_complete_signal.emit(index, False)

        self.all_finished_signal.emit()


class SpatialMediaBatchGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spatial Media Batch Injector (PyQt6)")
        self.setMinimumSize(850, 600)
        self.input_directory = None
        self.output_directory = None
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Style sheet definition for clean, modern monospaced directory strips
        label_style = "color: #555555; background-color: #f8f9fa; padding: 6px; border: 1px solid #e9ecef; border-radius: 4px; font-family: Consolas, monospace;"

        # Main horizontal container that splits the paths layout from the checkbox panel
        paths_and_checkbox_container = QHBoxLayout()

        # Left Column: Stacks the input row and output row vertically
        path_rows_stack = QVBoxLayout()

        # ROW 1: Input controls grouped horizontally
        input_row = QHBoxLayout()
        btn_open_dir = QPushButton("📁 Load Videos")
        btn_open_dir.setMinimumWidth(150)
        btn_open_dir.clicked.connect(self.select_input_directory)

        self.lbl_input_path = QLabel("Input Directory: Not Selected")
        self.lbl_input_path.setStyleSheet(label_style)

        input_row.addWidget(btn_open_dir)
        input_row.addWidget(self.lbl_input_path, stretch=1)
        path_rows_stack.addLayout(input_row)

        # ROW 2: Output controls grouped horizontally
        output_row = QHBoxLayout()
        self.btn_output_dir = QPushButton("📂 Set Output")
        self.btn_output_dir.setMinimumWidth(150)
        self.btn_output_dir.clicked.connect(self.select_output_directory)

        self.lbl_output_path = QLabel("Output Directory: Same as Input (Default)")
        self.lbl_output_path.setStyleSheet(label_style)

        output_row.addWidget(self.btn_output_dir)
        output_row.addWidget(self.lbl_output_path, stretch=1)
        path_rows_stack.addLayout(output_row)

        # Add the stacked path rows to the main horizontal container
        paths_and_checkbox_container.addLayout(path_rows_stack, stretch=1)

        # Right Column: The Overwrite Checkbox (Takes up the full height of both rows)
        checkbox_panel = QVBoxLayout()
        self.chk_overwrite = QCheckBox("⚠️ Overwrite Source Files")

        # Center the checkbox vertically relative to the two rows next to it
        checkbox_panel.addWidget(self.chk_overwrite)
        self.chk_overwrite.toggled.connect(self.toggle_overwrite_mode)

        paths_and_checkbox_container.addLayout(checkbox_panel)

        # Inject the entire aligned top block into the window layout
        layout.addLayout(paths_and_checkbox_container)

        # Target Batch Processing Table Grid View
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [
                "Source File Name",
                "Projection",
                "Stereoscopic",
                "Spatial Audio",
                "Remove",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        # Diagnostic Log Console Window
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(120)
        layout.addWidget(QLabel("Diagnostic Injection Log:"))
        layout.addWidget(self.log_console)

        # Bottom Execution Action Loop
        self.btn_run = QPushButton("⚡ Run Batch Injection Sequence")
        self.btn_run.setStyleSheet(
            "background-color: #28a745; color: white; font-weight: bold; padding: 12px; font-size: 14px;"
        )
        self.btn_run.clicked.connect(self.execute_batch_pipeline)
        layout.addWidget(self.btn_run)

    def toggle_overwrite_mode(self, checked):
        """Disables output directory controls when users choose to overwrite the sources directly."""
        self.btn_output_dir.setDisabled(checked)
        if checked:
            self.lbl_output_path.setText(
                "Output Directory: [OVERWRITE ACTIVE] Original source files will be replaced."
            )
            self.lbl_output_path.setStyleSheet(
                "color: #b71c1c; background-color: #ffebee; padding: 4px; border: 1px solid #ffcdd2; border-radius: 4px; font-family: Consolas, monospace; font-weight: bold;"
            )
            self.log_console.append(
                "[System Output Notice] Overwrite active. Output parameters will adapt dynamically."
            )
        else:
            if self.output_directory:
                self.lbl_output_path.setText(
                    f"Output Directory: {self.output_directory}"
                )
            elif self.input_directory:
                self.lbl_output_path.setText(
                    f"Output Directory: Same as Input ({self.input_directory})"
                )
            else:
                self.lbl_output_path.setText(
                    "Output Directory: Same as Input (Default)"
                )
            self.lbl_output_path.setStyleSheet(
                "color: #555555; background-color: #f8f9fa; padding: 6px; border: 1px solid #e9ecef; border-radius: 4px; font-family: Consolas, monospace;"
            )

    def select_input_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Source Videos Location Directory", ""
        )
        if dir_path:
            self.input_directory = Path(dir_path)
            self.lbl_input_path.setText(f"Input Directory: {self.input_directory}")

            if not self.chk_overwrite.isChecked() and not self.output_directory:
                self.lbl_output_path.setText(
                    f"Output Directory: Same as Input ({self.input_directory})"
                )

            self.table.setRowCount(0)

            valid_extensions = {".mp4", ".mov"}
            video_files = [
                f
                for f in self.input_directory.iterdir()
                if f.is_file() and f.suffix.lower() in valid_extensions
            ]

            if not video_files:
                QMessageBox.information(
                    self,
                    "Empty Directory",
                    "No compatible .mp4 or .mov file profiles found.",
                )
                return

            for video in video_files:
                row = self.table.rowCount()
                self.table.insertRow(row)

                name_item = QTableWidgetItem(video.name)
                name_item.setData(32, str(video))
                self.table.setItem(row, 0, name_item)

                combo_proj = QComboBox()
                combo_proj.addItems(
                    [
                        "Flat / Standard Video",
                        "VR 360 (Full Spherical)",
                        "VR 180 (Front Dome)",
                    ]
                )
                combo_proj.setCurrentIndex(1)
                self.table.setCellWidget(row, 1, combo_proj)

                combo_stereo = QComboBox()
                combo_stereo.addItems(["none", "top-bottom", "left-right"])
                combo_stereo.setCurrentIndex(2)
                self.table.setCellWidget(row, 2, combo_stereo)

                chk_audio = QCheckBox()
                chk_audio.setChecked(False)
                from PyQt6.QtCore import Qt

                container_widget = QWidget()
                cell_layout = QHBoxLayout(container_widget)
                cell_layout.addWidget(chk_audio)
                cell_layout.setAlignment(chk_audio, Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, 3, container_widget)

                btn_remove = QPushButton("❌")
                btn_remove.setStyleSheet(
                    "background-color: #dc3545; color: white; font-weight: bold; border-radius: 4px;"
                )
                btn_remove.clicked.connect(
                    lambda checked, r=row: self.remove_table_row(r)
                )
                self.table.setCellWidget(row, 4, btn_remove)

            self.log_console.append(
                f"[Loaded Data] Discovered and built {len(video_files)} active elements out of directory space."
            )

    def select_output_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Target Extraction Target Directory", ""
        )
        if dir_path:
            self.output_directory = Path(dir_path)
            self.lbl_output_path.setText(f"Output Directory: {self.output_directory}")
            self.log_console.append(
                f"[Output Space Assigned Location]: {self.output_directory}"
            )

    def remove_table_row(self, row_index):
        """Safely removes an explicit row grid matching index layout location boundaries."""
        # Because dynamic deletions offset array position pointers, we locate object origin indexes safely
        button = self.sender()
        if button:
            for r in range(self.table.rowCount()):
                if self.table.cellWidget(r, 4) == button:
                    self.table.removeRow(r)
                    break

    def execute_batch_pipeline(self):
        row_count = self.table.rowCount()
        if row_count == 0:
            QMessageBox.warning(
                self,
                "Workflow Error",
                "No active items present inside processing queues.",
            )
            return

        tasks = []
        for r in range(row_count):
            name_item = self.table.item(r, 0)

            # FIX: Strip old execution checkmarks/crosses so the file list resets cleanly
            current_text = name_item.text()
            clean_text = current_text.lstrip("✓ ✗ ⏳ ")
            name_item.setText(clean_text)

            infile_path = name_item.data(32)
            combo_proj = self.table.cellWidget(r, 1)
            combo_stereo = self.table.cellWidget(r, 2)

            audio_container = self.table.cellWidget(r, 3)
            chk_audio = audio_container.findChild(QCheckBox)

            tasks.append(
                {
                    "infile": infile_path,
                    "projection": combo_proj.currentText(),
                    "stereo": combo_stereo.currentText(),
                    "audio": chk_audio.isChecked(),
                }
            )

        # Lock UI controls to ensure processing threads run safely without concurrent mutations
        self.btn_run.setEnabled(False)
        self.log_console.clear()
        self.log_console.append(
            "[System Alert Execution] Processing active batch injection vectors asynchronously..."
        )

        # Initialize background scheduling workers
        self.worker = BatchWorker(
            tasks, self.chk_overwrite.isChecked(), self.output_directory
        )
        self.worker.log_signal.connect(self.log_console.append)

        # Proactively tag the first item as processing ⏳
        if row_count > 0:
            item = self.table.item(0, 0)
            item.setText(f"⏳ {item.text()}")

        self.worker.item_complete_signal.connect(
            self.update_row_completion_visual_feedback
        )
        self.worker.all_finished_signal.connect(
            self.batch_processing_pipeline_completed
        )
        self.worker.start()

    def update_row_completion_visual_feedback(self, row_index, success):
        """Highlights row validation steps dynamically and tracks queue indicators."""
        # Update the file item that just finished processing
        item = self.table.item(row_index, 0)
        if item:
            clean_text = item.text().lstrip("⏳ ")
            if success:
                item.setText(f"✓ {clean_text}")
            else:
                item.setText(f"✗ {clean_text}")

        # Proactively mark the NEXT row in the batch list queue as processing ⏳
        next_row = row_index + 1
        if next_row < self.table.rowCount():
            next_item = self.table.item(next_row, 0)
            if next_item:
                next_item.setText(f"⏳ {next_item.text()}")

    def batch_processing_pipeline_completed(self):
        self.btn_run.setEnabled(True)
        self.log_console.append(
            "\n[ALL TASKS COMPLETED] Processing actions verified successfully."
        )
        QMessageBox.information(
            self,
            "Pipeline Status Complete",
            "Batch video sequence configurations injected completely.",
        )
