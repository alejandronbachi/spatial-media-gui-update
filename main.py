import sys

from PyQt6.QtWidgets import QApplication

from spatialmedia.gui import SpatialMediaBatchGui


def main():
    app = QApplication(sys.argv)
    window = SpatialMediaBatchGui()
    QApplication.setStyle("Fusion")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
