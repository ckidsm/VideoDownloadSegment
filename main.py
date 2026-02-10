import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui import App

def main():
    app = QApplication(sys.argv)
    w = App()
    w.show()

    # macOS 번들 앱에서 키보드 입력을 위해 창 활성화
    def activate():
        w.raise_()
        w.activateWindow()
    QTimer.singleShot(100, activate)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
