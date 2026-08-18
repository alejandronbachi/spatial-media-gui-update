import os
import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import the original underlying spatial-media core logic
from . import metadata_utils


class InjectorWorker(QThread):
    """Worker thread to handle file injection without freezing the main GUI thread."""

    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, infile, outfile, metadata):
        super().__init__()
        self.infile = infile
        self.outfile = outfile
        self.metadata = metadata

    def run(self):
        try:

            def local_logger(msg):
                self.status_signal.emit(msg)

            # Call the native spatial-media utility function safely on a background thread
            metadata_utils.inject_metadata(
                self.infile, self.outfile, self.metadata, local_logger
            )
            self.finished_signal.emit(True, self.outfile)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class SpatialMediaGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spatial Media Metadata Injector (PyQt6 Edition)")
        self.setMinimumSize(550, 450)
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # File Chooser Section
        file_layout = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Select a video file (MP4/MOV)...")
        btn_browse = QPushButton("Open File")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(btn_browse)
        layout.addWidget(QLabel("Input Video File:"))
        layout.addLayout(file_layout)

        # Spatial Media Options Checklist
        self.chk_spherical = QCheckBox("My video is spherical (360 degrees)")
        self.chk_spatial_audio = QCheckBox("My video has spatial audio (Ambisonics)")
        layout.addWidget(self.chk_spherical)
        layout.addWidget(self.chk_spatial_audio)

        # Stereo Dropdown Options
        stereo_layout = QHBoxLayout()
        stereo_layout.addWidget(QLabel("Stereoscopic Mode:"))
        self.combo_stereo = QComboBox()
        self.combo_stereo.addItems(["none", "top-bottom", "left-right"])
        stereo_layout.addWidget(self.combo_stereo)
        layout.addLayout(stereo_layout)

        # Process Log Window
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        layout.addWidget(QLabel("Process Log:"))
        layout.addWidget(self.log_console)

        # Injection Action Button
        self.btn_inject = QPushButton("Inject Metadata")
        self.btn_inject.setStyleSheet(
            "background-color: #007ACC; color: white; font-weight: bold; padding: 8px;"
        )
        self.btn_inject.clicked.connect(self.start_injection)
        layout.addWidget(self.btn_inject)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", "", "Videos (*.mp4 *.mov)"
        )
        if file_path:
            self.file_input.setText(file_path)
            self.log_console.append(f"Loaded: {os.path.basename(file_path)}")

    def start_injection(self):
        infile = self.file_input.text()
        if not infile or not os.path.exists(infile):
            QMessageBox.warning(
                self, "Error", "Please select a valid input video file."
            )
            return

        # Prepare target output names
        base, ext = os.path.splitext(infile)
        outfile = f"{base}_injected{ext}"

        # Populate internal parsed Metadata object models structured by google/spatial-media
        metadata = metadata_utils.Metadata()
        metadata.video = metadata_utils.VideoMetadata()
        metadata.video.spherical = self.chk_spherical.isChecked()
        metadata.video.stereo = self.combo_stereo.currentText()
        metadata.audio = (
            metadata_utils.AudioMetadata()
            if self.chk_spatial_audio.isChecked()
            else None
        )

        self.btn_inject.setEnabled(False)
        self.log_console.append("Starting parsing process...")

        # Initialize background worker execution
        self.worker = InjectorWorker(infile, outfile, metadata)
        self.worker.status_signal.connect(self.log_console.append)
        self.worker.finished_signal.connect(self.injection_completed)
        self.worker.start()

    def injection_completed(self, success, result):
        self.btn_inject.setEnabled(True)
        if success:
            QMessageBox.information(
                self,
                "Success",
                f"Spatial metadata injected successfully!\nSaved to: {result}",
            )
            self.log_console.append(
                f"\n[DONE] Saved new target video file to:\n{result}"
            )
        else:
            QMessageBox.critical(self, "Execution Error", f"Failed: {result}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpatialMediaGui()
    window.show()
    sys.exit(app.exec())
