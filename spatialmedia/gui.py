import sys
from pathlib import Path

import qdarktheme
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
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
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import the core engine tools
from spatialmedia import metadata_utils


def resolve_resource_path(relative_path):
    """Get the absolute path to a resource, handling PyInstaller temporary runtime paths safely."""
    try:
        # If running inside a compiled PyInstaller .exe, use its secret temp folder path
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # If running as raw source code in VS Code, use the repository root folder path
        # (This walks up one level from spatialmedia/gui.py to reach the root folder)
        base_path = Path(__file__).resolve().parent.parent

    return base_path / relative_path


class BatchWorker(QThread):
    """Handles parsing and shifting media metadata asynchronously to prevent GUI freezing."""

    log_signal = pyqtSignal(str)
    item_complete_signal = pyqtSignal(int, bool)
    all_finished_signal = pyqtSignal()

    def __init__(self, tasks, overwrite_source, output_dir):
        super().__init__()
        self.tasks = tasks
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

            # FIX: File-by-file runtime calculation. If no custom global output dir is set,
            # it defaults target output generation directly to the parent folder of THIS specific video file.
            if self.output_dir and not self.overwrite_source:
                temp_outfile = (
                    self.output_dir / f"{infile.stem}_injected{infile.suffix}"
                )
            else:
                temp_outfile = infile.parent / f"{infile.stem}_injected{infile.suffix}"

            try:
                metadata = metadata_utils.Metadata()
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

                metadata_utils.inject_metadata(
                    str(infile), str(temp_outfile), metadata, silent_logger
                )

                if temp_outfile.exists() and temp_outfile.stat().st_size > 0:
                    if self.overwrite_source:
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
        self.output_directory = None

        # NEW: Enable global drag and drop capture states on the main window frame
        self.setAcceptDrops(True)
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        label_style = "color: #555555; background-color: #f8f9fa; padding: 6px; border: 1px solid #e9ecef; border-radius: 4px; font-family: Consolas, monospace;"

        paths_and_checkbox_container = QHBoxLayout()
        path_rows_stack = QVBoxLayout()

        # ROW 1: Input controls updated with your text preferences
        input_row = QHBoxLayout()
        btn_open_dir = QPushButton("Load Videos")
        btn_open_dir.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        btn_open_dir.setMinimumWidth(150)
        btn_open_dir.clicked.connect(self.select_input_directory_picker)

        # Updated text to reflect both folder pickers and drag-and-drop operations
        self.lbl_input_path = QLabel(
            "Input Source Status: Queue empty (Drag & Drop files or folders here)"
        )
        self.lbl_input_path.setStyleSheet(label_style)

        input_row.addWidget(btn_open_dir)
        input_row.addWidget(self.lbl_input_path, stretch=1)
        path_rows_stack.addLayout(input_row)

        # ROW 2: Output controls updated with your text preferences
        output_row = QHBoxLayout()
        self.btn_output_dir = QPushButton("Set Output")
        self.btn_output_dir.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
        )
        self.btn_output_dir.setMinimumWidth(150)
        self.btn_output_dir.clicked.connect(self.select_output_directory)

        self.lbl_output_path = QLabel(
            "Output Directory: Same as Input files parent folders (Default)"
        )
        self.lbl_output_path.setStyleSheet(label_style)

        output_row.addWidget(self.btn_output_dir)
        output_row.addWidget(self.lbl_output_path, stretch=1)
        path_rows_stack.addLayout(output_row)

        paths_and_checkbox_container.addLayout(path_rows_stack, stretch=1)

        checkbox_panel = QVBoxLayout()
        self.chk_overwrite = QCheckBox("Overwrite Source Files")
        self.chk_overwrite.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        )
        checkbox_panel.addWidget(self.chk_overwrite)
        self.chk_overwrite.toggled.connect(self.toggle_overwrite_mode)

        paths_and_checkbox_container.addLayout(checkbox_panel)
        layout.addLayout(paths_and_checkbox_container)

        # Target Table Grid View
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

        # Acquire a pointer control object to the horizontal header configuration engine
        header = self.table.horizontalHeader()

        # COLUMN 0: Let the file name stretch dynamically to occupy all remaining wide space
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # COLUMNS 1 & 2: Lock the dropdown menus to a fixed, safe size so they are perfectly legible
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 160)  # Ample space for "VR 360 (Full Spherical)"

        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 130)  # Ample space for "left-right" / "top-bottom"

        # COLUMN 3: Lock the spatial audio checkbox column tightly around its content bounds
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 100)

        # COLUMN 4: Scale the trash bin column precisely down to a small functional utility footprint
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 75)

        layout.addWidget(self.table)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(120)
        layout.addWidget(QLabel("Diagnostic Injection Log:"))
        layout.addWidget(self.log_console)

        # Bottom Execution Action Loop
        # Centered Layout Alignment Wrapper for the Action Button
        run_button_layout = QHBoxLayout()
        # Add a stretch spacer on the left side to push the button to the center
        run_button_layout.addStretch(1)
        self.btn_run = QPushButton("⚡ Inject videos")
        # Give the button a fixed minimum width so it looks substantial but not overwhelming
        self.btn_run.setMinimumWidth(220)
        self.btn_run.setStyleSheet(
            "background-color: #ffc107; color: #212529; font-weight: bold; padding: 12px 24px; font-size: 14px; border-radius: 4px;"
        )
        self.btn_run.clicked.connect(self.execute_batch_pipeline)
        run_button_layout.addWidget(self.btn_run)

        # Add a stretch spacer on the right side to balance it out perfectly
        run_button_layout.addStretch(1)

        # Inject the centered sub-layout into the window's main layout stack
        layout.addLayout(run_button_layout)

        # Load your icon using the dynamic resource path resolver

        icon_path = resolve_resource_path("assets/icons/app_icon.png")

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            self.setWindowIconText("SpatialMediaBatchInjector")
        else:
            self.log_console.append(
                f"[Warning] Window icon graphic asset missing at path: {icon_path.name}"
            )
        qdarktheme.setup_theme("dark")

    # ==========================================
    # NEW: DRAG AND DROP INTERACTION EVENT HANDLERS
    # ==========================================
    def dragEnterEvent(self, event):
        """Fires when items are dragged over the window frame bounds."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()  # Accept operation and morph cursor to copy flag "+"

    def dropEvent(self, event):
        """Fires when items are dropped/released onto the window canvas."""
        discovered_paths = []
        valid_extensions = {".mp4", ".mov"}

        for url in event.mimeData().urls():
            local_path = Path(url.toLocalFile())

            if local_path.is_dir():
                # Scenario A: User dropped a whole directory folder -> scan its flat layout contents
                for file_item in local_path.iterdir():
                    if (
                        file_item.is_file()
                        and file_item.suffix.lower() in valid_extensions
                    ):
                        discovered_paths.append(file_item)
            elif local_path.is_file() and local_path.suffix.lower() in valid_extensions:
                # Scenario B: User dropped an individual video file profile or selected array
                discovered_paths.append(local_path)

        if discovered_paths:
            self.add_files_to_queue(discovered_paths)
            event.acceptProposedAction()
        else:
            QMessageBox.information(
                self,
                "No Videos Found",
                "Dropped items did not contain valid .mp4 or .mov video assets.",
            )

    # ==========================================
    # REFACTORED: UNIFIED PIPELINE FILE LOADER
    # ==========================================
    def add_files_to_queue(self, file_paths):
        """Unified queue processing engine. Shared between folder pickers and drop events."""
        # Collate list entries to filter out duplicates that are already inside our grid rows
        existing_paths = set()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item:
                existing_paths.add(item.data(Qt.ItemDataRole.UserRole))

        added_count = 0
        for video in file_paths:
            # Skip if file path is already present in queue
            if str(video) in existing_paths:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # File Display Item Configuration
            # ... (Inside the loop of add_files_to_queue)
            name_item = QTableWidgetItem(video.name)
            name_item.setData(
                Qt.ItemDataRole.UserRole, str(video)
            )  # Unified Qt data slot mapping
            self.table.setItem(row, 0, name_item)

            # Dropdown Elements Mapping
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
            container_widget = QWidget()
            cell_layout = QHBoxLayout(container_widget)
            cell_layout.addWidget(chk_audio)
            cell_layout.setAlignment(chk_audio, Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 3, container_widget)

            # Add deletion cleanup action triggers dynamically
            btn_remove = QPushButton()
            btn_remove.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
            )
            btn_remove.setStyleSheet(
                "border: none; background: transparent; padding: 2px;"
            )
            # Add a slight hover effect style sheet rule to make it interactive
            btn_remove.setToolTip("Remove video from queue")

            btn_remove.clicked.connect(lambda checked: self.remove_table_row())
            self.table.setCellWidget(row, 4, btn_remove)

            added_count += 1

        # Dynamic notification UI response updating total count status strings
        self.update_input_directory_label()
        self.log_console.append(
            f"[Loaded Data] Appended {added_count} new item(s) safely into execution queues."
        )

    def update_input_directory_label(self):
        """Scans loaded table items dynamically to present the input routing summary."""
        total_items = self.table.rowCount()
        if total_items == 0:
            self.lbl_input_path.setText(
                "Input Source Status: Queue empty (Drag & Drop files or folders here)"
            )
            return

        # Collate unique folder nodes using a set structure
        unique_dirs = set()
        for r in range(total_items):
            item = self.table.item(r, 0)
            if item:
                file_path = Path(item.data(Qt.ItemDataRole.UserRole))
                unique_dirs.add(file_path.parent)

        if len(unique_dirs) == 1:
            # Exactly one distinct folder origin -> present its absolute path string location
            self.lbl_input_path.setText(f"Input Directory: {list(unique_dirs)[0]}")
        else:
            # Elements originate from different directories -> trigger Multiple Sources notification
            self.lbl_input_path.setText("Input Directory: Multiple Sources")

    def select_input_directory_picker(self):
        """Triggered strictly when users click the manual folder picker button."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Source Videos Location Directory", ""
        )
        if dir_path:
            input_dir = Path(dir_path)
            valid_extensions = {".mp4", ".mov"}
            video_files = [
                f
                for f in input_dir.iterdir()
                if f.is_file() and f.suffix.lower() in valid_extensions
            ]

            if not video_files:
                QMessageBox.information(
                    self,
                    "Empty Directory",
                    "No compatible .mp4 or .mov file profiles found.",
                )
                return

            # Send discovered list directly down into our refactored unified loader method
            self.add_files_to_queue(video_files)

    def toggle_overwrite_mode(self, checked):
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
            else:
                self.lbl_output_path.setText(
                    "Output Directory: Same as Input files parent folders (Default)"
                )
            self.lbl_output_path.setStyleSheet(
                "color: #555555; background-color: #f8f9fa; padding: 6px; border: 1px solid #e9ecef; border-radius: 4px; font-family: Consolas, monospace;"
            )
            self.log_console.append(
                "[System Output Notice] Overwrite disabled. Modified files will be exported as separate files with '_injected' added to their names."
            )

    def remove_table_row(self):
        button = self.sender()
        if button:
            for r in range(self.table.rowCount()):
                if self.table.cellWidget(r, 4) == button:
                    self.table.removeRow(r)
                    break

        self.update_input_directory_label()

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
            current_text = name_item.text()
            clean_text = current_text.lstrip("✓ ✗ ⏳ ")
            name_item.setText(clean_text)

            # Access underlying unified key via exact user role enum mappings
            infile_path = name_item.data(Qt.ItemDataRole.UserRole)
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

        self.btn_run.setEnabled(False)
        self.log_console.clear()
        self.log_console.append(
            "[System Alert Execution] Processing active batch injection vectors asynchronously..."
        )

        self.worker = BatchWorker(
            tasks, self.chk_overwrite.isChecked(), self.output_directory
        )
        self.worker.log_signal.connect(self.log_console.append)

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
        """Highlights row status indicators dynamically with clean readability contrasts."""
        # Acquire standard text item pointers safely
        item = self.table.item(row_index, 0)
        if item:
            clean_text = item.text().lstrip("⏳ ")
            if success:
                item.setText(f"✓ {clean_text}")
                # Strong, accessible high-contrast green text layout pattern
                item.setBackground(QColor("#d4edda"))
                item.setForeground(QColor("#155724"))
            else:
                item.setText(f"✗ {clean_text}")
                # High-contrast accessibility dark red text metrics matching light error backgrounds
                item.setBackground(QColor("#f8d7da"))
                item.setForeground(QColor("#721c24"))

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
