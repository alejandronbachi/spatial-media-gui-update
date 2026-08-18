import sys

from PyQt6.QtWidgets import QApplication

# Clean, top-level absolute import
from spatialmedia.gui import SpatialMediaGui


def main():
    app = QApplication(sys.argv)
    window = SpatialMediaGui()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
