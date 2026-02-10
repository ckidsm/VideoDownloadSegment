# SegmentGrabber

비디오 세그먼트 다운로더 (PyQt6)

## 프로젝트 구조

```
├── main.py              # 진입점
├── ui.py                # UI 코드
├── workers.py           # 다운로드 워커
├── models.py            # 데이터 모델
├── utils.py             # 유틸리티
├── Videofragment.py     # (이전 버전)
├── requirements.txt     # 의존성
├── build_macos.sh       # macOS 빌드
├── build_windows.bat    # Windows 빌드
├── SegmentGrabber.spec  # PyInstaller 스펙
├── venv/                # 가상환경
├── Save/                # 다운로드 폴더
├── build/               # 빌드 임시파일
└── dist/                # 실행파일 출력
```

## 실행 방법

### 소스에서 실행
```bash
pip install -r requirements.txt
python main.py
```

### 빌드 (실행파일 생성)

**macOS:**
```bash
./build_macos.sh
# 결과: dist/SegmentGrabber.app
```

**Windows:**
```batch
build_windows.bat
# 결과: dist\SegmentGrabber.exe
```

## 최종 업데이트
2026-01-17
