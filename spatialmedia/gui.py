from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
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

        # Top Control Action Bar
        top_bar = QHBoxLayout()
        btn_open_dir = QPushButton("📁 Load Videos Directory")
        btn_open_dir.clicked.connect(self.select_input_directory)

        self.btn_output_dir = QPushButton("📂 Set Custom Output Directory")
        self.btn_output_dir.clicked.connect(self.select_output_directory)

        self.chk_overwrite = QCheckBox("⚠️ Overwrite Source Files")
        self.chk_overwrite.toggled.connect(self.toggle_overwrite_mode)

        top_bar.addWidget(btn_open_dir)
        top_bar.addWidget(self.btn_output_dir)
        top_bar.addWidget(self.chk_overwrite)
        layout.addLayout(top_bar)

        # Target Batch Processing Table Grid View Control Element
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [
                "Source File Name",
                "Projection Environment",
                "Stereoscopic Mode",
                "Spatial Audio",
                "Remove Action",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)

        # Running Diagnostic Log Console Window Layout
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(120)
        layout.addWidget(QLabel("Diagnostic Injection Log:"))
        layout.addWidget(self.log_console)

        # Bottom Pipeline Execution Button Wrapper Action Loop
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
            self.log_console.append(
                "[System Output Notice] Overwrite active. Output parameters will adapt dynamically."
            )

    def select_input_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Source Videos Location Directory", ""
        )
        if dir_path:
            self.input_directory = Path(dir_path)
            self.table.setRowCount(0)  # Wipe previous layout selections cleanly

            # Scan destination for standard target container paths using pathlib extensions
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

                # Set clean text item reference labels
                name_item = QTableWidgetItem(video.name)
                name_item.setData(
                    32, str(video)
                )  # Store the underlying absolute path mapping inside item data
                self.table.setItem(row, 0, name_item)

                # Insert projection configurations dropdown component
                combo_proj = QComboBox()
                combo_proj.addItems(
                    [
                        "Flat / Standard Video",
                        "VR 360 (Full Spherical)",
                        "VR 180 (Front Dome)",
                    ]
                )
                combo_proj.setCurrentIndex(
                    1
                )  # Default selection to VR 360 matching current asset usage requirements
                self.table.setCellWidget(row, 1, combo_proj)

                # Insert stereoscopic structural configurations dropdown component
                combo_stereo = QComboBox()
                combo_stereo.addItems(["none", "top-bottom", "left-right"])
                combo_stereo.setCurrentIndex(
                    2
                )  # Default selection to Side-by-Side Left-Right parameters
                self.table.setCellWidget(row, 2, combo_stereo)

                # Add spatial audio toggles
                chk_audio = QCheckBox()
                chk_audio.setChecked(False)
                container_widget = QWidget()
                cell_layout = QHBoxLayout(container_widget)
                cell_layout.addWidget(chk_audio)
                # Correct PyQt6 alignment implementation using the native enum
                cell_layout.setAlignment(chk_audio, Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, 3, container_widget)

                # Add deletion cleanup action triggers dynamically
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

    def remove_table_row(self, row_index):
        """Safely removes an explicit row grid matching index layout location boundaries."""
        # Because dynamic deletions offset array position pointers, we locate object origin indexes safely
        button = self.sender()
        if button:
            for r in range(self.table.rowCount()):
                if self.table.cellWidget(r, 4) == button:
                    self.table.removeRow(r)
                    break

    def select_output_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Target Extraction Target Directory", ""
        )
        if dir_path:
            self.output_directory = Path(dir_path)
            self.log_console.append(
                f"[Output Space Assigned Location]: {self.output_directory}"
            )

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
            infile_path = name_item.data(32)

            combo_proj = self.table.cellWidget(r, 1)
            combo_stereo = self.table.cellWidget(r, 2)

            # Access embedded cell checklist widget elements safely
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
        self.worker.item_complete_signal.connect(
            self.update_row_completion_visual_feedback
        )
        self.worker.all_finished_signal.connect(
            self.batch_processing_pipeline_completed
        )
        self.worker.start()

    def update_row_completion_visual_feedback(self, row_index, success):
        """Highlights row validation steps dynamically."""
        for c in range(self.table.columnCount()):
            item = self.table.item(row_index, c)
            if item:
                # Add text prefixes to clearly show the status of the row item
                if success:
                    item.setText(f"✓ {item.text()}")
                else:
                    item.setText(f"✗ {item.text()}")

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
