import sys
from PyQt6.QtWidgets import QApplication
from ui import App

def main():
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
