# ui.py
import os
import re
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QMessageBox, QTextEdit, QSpinBox, QRadioButton, QButtonGroup
)

from models import JobConfig, VideoType
from workers import DownloadWorker, PornhubDownloadWorker
from utils import parse_headers_text


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Segment Grabber (PyQt6)")
        self.resize(980, 560)

        v = QVBoxLayout(self)

        # ── 입력 라인
        form = QHBoxLayout()
        self.url_edit = QLineEdit()
        form.addWidget(QLabel("원본 URL(폴더)"))
        form.addWidget(self.url_edit, 1)

        self.outname_edit = QLineEdit("output.mp4")
        form.addWidget(QLabel("저장이름"))
        form.addWidget(self.outname_edit)

        self.dir_edit = QLineEdit("save")
        self.dir_edit.setPlaceholderText("(비우면 현재 경로)")
        btn_dir = QPushButton("경로…")
        btn_dir.clicked.connect(self.choose_dir)
        form.addWidget(QLabel("저장경로"))
        form.addWidget(self.dir_edit, 1)
        form.addWidget(btn_dir)
        v.addLayout(form)

        # ── 비디오 소스 선택
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("비디오 소스:"))
        self.yasya_radio = QRadioButton("Yasya (세그먼트)")
        self.porn_radio = QRadioButton("Pornhub")
        self.yasya_radio.setChecked(True)

        self.source_group = QButtonGroup(self)
        self.source_group.addButton(self.yasya_radio)
        self.source_group.addButton(self.porn_radio)

        source_layout.addWidget(self.yasya_radio)
        source_layout.addWidget(self.porn_radio)
        source_layout.addStretch()
        v.addLayout(source_layout)

        # ── 고급 옵션
        adv = QHBoxLayout()

        # 자동 탐지 체크박스
        self.auto_detect_chk = QCheckBox("자동 탐지")
        self.auto_detect_chk.setChecked(True)
        self.auto_detect_chk.setToolTip("시작/끝 번호를 자동으로 탐지합니다")
        self.auto_detect_chk.stateChanged.connect(self._on_auto_detect_changed)
        adv.addWidget(self.auto_detect_chk)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(1)
        self.start_spin.setEnabled(False)  # 자동 탐지 시 비활성화
        adv.addWidget(QLabel("시작번호"))
        adv.addWidget(self.start_spin)

        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 999999)
        self.end_spin.setSpecialValueText("0=모름")
        self.end_spin.setValue(0)
        self.end_spin.setEnabled(False)  # 자동 탐지 시 비활성화
        adv.addWidget(QLabel("끝번호(0=모름)"))
        adv.addWidget(self.end_spin)

        self.pad_spin = QSpinBox()
        self.pad_spin.setRange(1, 8)
        self.pad_spin.setValue(4)
        adv.addWidget(QLabel("자릿수"))
        adv.addWidget(self.pad_spin)

        self.stop404_spin = QSpinBox()
        self.stop404_spin.setRange(1, 100)
        self.stop404_spin.setValue(10)
        self.stop404_spin.setEnabled(False)  # 자동 탐지 시 비활성화
        adv.addWidget(QLabel("연속404 임계"))
        adv.addWidget(self.stop404_spin)
        v.addLayout(adv)

        # ── 헤더/쿠키 입력
        hdr_layout = QHBoxLayout()
        self.hdr_edit = QTextEdit()
        hdr_layout.addWidget(QLabel("Custom Headers"))
        hdr_layout.addWidget(self.hdr_edit, 1)
        v.addLayout(hdr_layout)

        # ── 버튼들
        btns = QHBoxLayout()
        self.btn_add = QPushButton("추가")
        self.btn_start = QPushButton("선택 다운로드 시작")
        self.btn_stop = QPushButton("선택 중지")
        self.btn_remove = QPushButton("선택 제거")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_remove)
        v.addLayout(btns)

        self.btn_add.clicked.connect(self.add_job)
        self.btn_start.clicked.connect(self.start_selected)
        self.btn_stop.clicked.connect(self.stop_selected)
        self.btn_remove.clicked.connect(self.remove_selected)

        # ── 테이블
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["선택", "원본 URL", "저장경로", "저장이름", "진행상황"])
        # 모든 컬럼 크기 조절 가능하도록 설정
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # 기본 컬럼 너비 설정
        self.table.setColumnWidth(0, 50)   # 선택
        self.table.setColumnWidth(1, 400)  # 원본 URL
        self.table.setColumnWidth(2, 120)  # 저장경로
        self.table.setColumnWidth(3, 120)  # 저장이름
        self.table.setColumnWidth(4, 200)  # 진행상황
        v.addWidget(self.table)

        # QThread 기반 워커 관리
        self.workers: Dict[int, DownloadWorker] = {}

        # 저장이름 자동 증가 카운터
        self._job_counter = 0

        # 진행 상태 저장 (row -> {'text': str, 'updated': bool})
        self._progress_status: Dict[int, dict] = {}

        # 완료된 다운로드 행 추적
        self._completed_rows: set = set()

        # 1초마다 UI 업데이트 타이머
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_progress_labels)
        self._update_timer.start(1000)

    # ---------- helpers ----------
    def _on_auto_detect_changed(self, state):
        """자동 탐지 체크박스 상태 변경 시"""
        enabled = state != Qt.CheckState.Checked.value
        self.start_spin.setEnabled(enabled)
        self.end_spin.setEnabled(enabled)
        self.stop404_spin.setEnabled(enabled)

    def choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "저장 경로 선택")
        if d:
            self.dir_edit.setText(d)

    def _get_checkbox(self, row: int) -> Optional[QCheckBox]:
        w = self.table.cellWidget(row, 0)
        if isinstance(w, QCheckBox):
            return w
        if w is not None:
            cb = w.findChild(QCheckBox)
            if isinstance(cb, QCheckBox):
                return cb
        return None

    def parse_headers(self) -> Dict[str, str]:
        return parse_headers_text(self.hdr_edit.toPlainText())

    def _sanitize_filename(self, name: str) -> str:
        """파일명을 안전하게 정제 (경로 순회 방지 + .mp4 자동 부여)"""
        name = (name or "output.mp4").strip()
        # 경로 구분자 및 상위 디렉토리 참조 제거
        name = name.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
        name = re.sub(r'\.\.+', '_', name)  # .. 제거
        # 파일명에 허용되지 않는 문자 제거 (Windows 호환)
        name = re.sub(r'[<>:"|?*]', '_', name)
        # 확장자 확인
        root, ext = os.path.splitext(name)
        if not root:
            root = "output"
        if not ext:
            ext = ".mp4"
        return root + ext

    def _cleanup_worker(self, row: int):
        """완료된 워커 정리"""
        if row in self.workers:
            worker = self.workers[row]
            if worker.isFinished():
                worker.deleteLater()
                del self.workers[row]

    def _generate_auto_filename(self) -> str:
        """자동 저장이름 생성 (output0001.mp4, output0002.mp4, ...)"""
        self._job_counter += 1
        return f"output{self._job_counter:04d}.mp4"

    def _update_progress_labels(self):
        """타이머로 1초마다 호출되어 진행 라벨 업데이트"""
        for row, status in list(self._progress_status.items()):
            if status.get('updated'):
                label = self.table.cellWidget(row, 4)
                if isinstance(label, QLabel):
                    label.setText(status['text'])
                status['updated'] = False

    def _on_progress(self, row: int, seg_idx: int, last_size: int):
        """프로그래스 시그널 핸들러 - 상태만 저장"""
        info = self._segment_info.get(row, {})
        if info.get('start') is not None and info.get('end') is not None:
            total = info['end'] - info['start'] + 1
            current = seg_idx - info['start'] + 1
            percent = int((current / total) * 100)
            text = f"{percent}% ({current}/{total}) - {last_size//1024} KB"
        else:
            text = f"{seg_idx} seg, {last_size//1024} KB"

        if row in self._progress_status:
            self._progress_status[row]['text'] = text
            self._progress_status[row]['updated'] = True

    def _on_pornhub_progress(self, row: int, downloaded: int, total: int):
        """Pornhub 다운로드 프로그래스 핸들러"""
        if total > 0:
            percent = int((downloaded / total) * 100)
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            text = f"{percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)"
        else:
            downloaded_mb = downloaded / (1024 * 1024)
            text = f"{downloaded_mb:.1f} MB"

        if row in self._progress_status:
            self._progress_status[row]['text'] = text
            self._progress_status[row]['updated'] = True

    def _on_status(self, row: int, msg: str):
        """상태 시그널 핸들러 - 상태만 저장"""
        if row in self._progress_status:
            self._progress_status[row]['text'] = msg
            self._progress_status[row]['updated'] = True

        # 탐지 완료 메시지에서 범위 파싱
        if "탐지 완료:" in msg:
            try:
                parts = msg.split(":")
                if len(parts) >= 2:
                    range_part = parts[1].split("(")[0].strip()
                    start_end = range_part.split("~")
                    if len(start_end) == 2:
                        if row not in self._segment_info:
                            self._segment_info[row] = {}
                        self._segment_info[row]['start'] = int(start_end[0].strip())
                        self._segment_info[row]['end'] = int(start_end[1].strip())
            except:
                pass

    def _on_done(self, row: int, success: bool, message: str):
        """완료 시그널 핸들러 - 즉시 업데이트"""
        text = ("완료: " if success else "실패: ") + message
        label = self.table.cellWidget(row, 4)
        if isinstance(label, QLabel):
            label.setText(text)
        if row in self._progress_status:
            self._progress_status[row]['text'] = text
            self._progress_status[row]['updated'] = False
        # 완료된 행으로 표시
        self._completed_rows.add(row)
        self._cleanup_worker(row)

    # ---------- actions ----------
    def add_job(self):
        try:
            self._add_job_impl()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"add_job error: {e}", flush=True)
            QMessageBox.critical(self, "오류", f"작업 추가 중 오류 발생:\n{str(e)}")

    def _add_job_impl(self):
        url = (self.url_edit.text() or "").strip()
        if not url:
            QMessageBox.warning(self, "입력 오류", "원본 URL을 입력하세요.")
            return
        save_dir = (self.dir_edit.text() or "save").strip()
        # 자동 저장이름 생성
        out_name = self._generate_auto_filename()

        row = self.table.rowCount()
        self.table.insertRow(row)

        # 체크박스를 중앙에 배치
        chk = QCheckBox()
        chk.setChecked(True)  # 자동 체크
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 0, chk_widget)

        self.table.setItem(row, 1, QTableWidgetItem(url))
        self.table.setItem(row, 2, QTableWidgetItem(save_dir))
        self.table.setItem(row, 3, QTableWidgetItem(out_name))

        # 진행상황 UI (텍스트 라벨)
        label = QLabel("대기 중")
        label.setStyleSheet("padding: 4px;")
        self.table.setCellWidget(row, 4, label)

        # 진행 상태 초기화
        self._progress_status[row] = {'text': '대기 중', 'updated': False}

        # URL 입력창 비우기
        self.url_edit.clear()

        # 새로 추가된 행만 다운로드 시작
        self._start_row(row)

    def _start_row(self, row: int):
        """특정 행의 다운로드 시작"""
        try:
            self._start_row_impl(row)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"_start_row error: {e}", flush=True)
            QMessageBox.critical(self, "오류", f"다운로드 시작 중 오류 발생:\n{str(e)}")

    def _start_row_impl(self, row: int):
        """특정 행의 다운로드 시작 (구현)"""
        # 헤더 파싱
        try:
            headers = self.parse_headers()
        except ValueError as e:
            QMessageBox.critical(self, "헤더 오류", str(e))
            return

        # 이미 실행 중인 워커가 있으면 스킵
        if row in self.workers and self.workers[row].isRunning():
            return

        # 이미 완료된 다운로드는 스킵
        if row in self._completed_rows:
            return

        # URL/경로/파일명
        url_item = self.table.item(row, 1)
        dir_item = self.table.item(row, 2)
        name_item = self.table.item(row, 3)
        if not url_item:
            return

        url_text = (url_item.text() or "").strip()
        if not url_text:
            return

        save_dir = (dir_item.text().strip() if dir_item and dir_item.text() else os.getcwd())
        raw_name = (name_item.text().strip() if name_item and name_item.text() else "output.mp4")
        out_name = self._sanitize_filename(raw_name)
        os.makedirs(save_dir, exist_ok=True)

        # 비디오 타입 결정
        video_type = VideoType.PORNHUB if self.porn_radio.isChecked() else VideoType.YASYA

        # 잡 설정
        auto_detect = self.auto_detect_chk.isChecked()
        cfg = JobConfig(
            base_folder_url=url_text,
            save_dir=save_dir,
            out_name=out_name,
            video_type=video_type,
            start=self.start_spin.value(),
            zero_pad=self.pad_spin.value(),
            end=(None if self.end_spin.value() == 0 else self.end_spin.value()),
            stop_after_n_404=self.stop404_spin.value(),
            retry=5,
            timeout=30,
            headers=headers,
            auto_detect=auto_detect,
        )

        # QThread 기반 워커 생성 (비디오 타입에 따라)
        if video_type == VideoType.PORNHUB:
            worker = PornhubDownloadWorker(cfg, parent=self)
        else:
            worker = DownloadWorker(cfg, parent=self)

        self.workers[row] = worker

        # 세그먼트 범위를 저장할 딕셔너리 초기화 (Yasya 전용)
        if video_type == VideoType.YASYA:
            if not hasattr(self, '_segment_info'):
                self._segment_info = {}
            self._segment_info[row] = {'start': None, 'end': None}

        # 시그널 핸들러 연결
        if video_type == VideoType.PORNHUB:
            # Pornhub는 다른 progress 시그널 (바이트 단위)
            worker.progress.connect(lambda downloaded, total, r=row: self._on_pornhub_progress(r, downloaded, total))
        else:
            worker.progress.connect(lambda seg, size, r=row: self._on_progress(r, seg, size))

        worker.status.connect(lambda msg, r=row: self._on_status(r, msg))
        worker.done.connect(lambda success, msg, r=row: self._on_done(r, success, msg))

        # QThread 시작
        worker.start()

    def start_selected(self):
        try:
            self._start_selected_impl()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"start_selected error: {e}", flush=True)
            QMessageBox.critical(self, "오류", f"다운로드 시작 중 오류 발생:\n{str(e)}")

    def _start_selected_impl(self):
        # 1) 헤더 파싱
        try:
            headers = self.parse_headers()
        except ValueError as e:
            QMessageBox.critical(self, "헤더 오류", str(e))
            return

        started = 0
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if not chk or not chk.isChecked():
                continue

            # 이미 실행 중인 워커가 있으면 스킵
            if row in self.workers and self.workers[row].isRunning():
                continue

            # 이미 완료된 다운로드는 스킵
            if row in self._completed_rows:
                continue

            # 기존 완료된 워커 정리
            self._cleanup_worker(row)

            # 2) URL/경로/파일명
            url_item = self.table.item(row, 1)
            dir_item = self.table.item(row, 2)
            name_item = self.table.item(row, 3)
            if not url_item:
                continue

            url_text = (url_item.text() or "").strip()
            if not url_text:
                continue

            save_dir = (dir_item.text().strip() if dir_item and dir_item.text() else os.getcwd())
            raw_name = (name_item.text().strip() if name_item and name_item.text() else "output.mp4")
            out_name = self._sanitize_filename(raw_name)
            os.makedirs(save_dir, exist_ok=True)

            # 3) 비디오 타입 결정
            video_type = VideoType.PORNHUB if self.porn_radio.isChecked() else VideoType.YASYA

            # 4) 잡 설정
            auto_detect = self.auto_detect_chk.isChecked()
            cfg = JobConfig(
                base_folder_url=url_text,
                save_dir=save_dir,
                out_name=out_name,
                video_type=video_type,
                start=self.start_spin.value(),
                zero_pad=self.pad_spin.value(),
                end=(None if self.end_spin.value() == 0 else self.end_spin.value()),
                stop_after_n_404=self.stop404_spin.value(),
                retry=5,
                timeout=30,
                headers=headers,
                auto_detect=auto_detect,
            )

            # 5) QThread 기반 워커 생성 (비디오 타입에 따라)
            if video_type == VideoType.PORNHUB:
                worker = PornhubDownloadWorker(cfg, parent=self)
            else:
                worker = DownloadWorker(cfg, parent=self)

            self.workers[row] = worker

            # 6) 세그먼트 범위를 저장할 딕셔너리 초기화 (Yasya 전용)
            if video_type == VideoType.YASYA:
                if not hasattr(self, '_segment_info'):
                    self._segment_info = {}
                self._segment_info[row] = {'start': None, 'end': None}

            # 7) 시그널 핸들러 연결
            if video_type == VideoType.PORNHUB:
                # Pornhub는 다른 progress 시그널 (바이트 단위)
                worker.progress.connect(lambda downloaded, total, r=row: self._on_pornhub_progress(r, downloaded, total))
            else:
                worker.progress.connect(lambda seg, size, r=row: self._on_progress(r, seg, size))

            worker.status.connect(lambda msg, r=row: self._on_status(r, msg))
            worker.done.connect(lambda success, msg, r=row: self._on_done(r, success, msg))

            # 8) QThread 시작
            worker.start()
            started += 1

        if started == 0:
            QMessageBox.information(self, "안내", "체크된 항목이 없거나 이미 실행 중입니다.")

    def stop_selected(self):
        """선택된 다운로드 중지"""
        stopped = 0
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if not chk or not chk.isChecked():
                continue
            if row in self.workers and self.workers[row].isRunning():
                self.workers[row].stop()
                stopped += 1

        if stopped == 0:
            QMessageBox.information(self, "안내", "중지할 항목이 없습니다.")

    def remove_selected(self):
        rows_to_remove = []
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk and chk.isChecked():
                # 실행 중인 워커가 있으면 중지
                if row in self.workers:
                    if self.workers[row].isRunning():
                        self.workers[row].stop()
                        self.workers[row].wait(1000)  # 최대 1초 대기
                    self.workers[row].deleteLater()
                    del self.workers[row]
                rows_to_remove.append(row)

        for offset, row in enumerate(rows_to_remove):
            self.table.removeRow(row - offset)

    def closeEvent(self, event):
        """앱 종료 시 모든 워커 정리"""
        for row, worker in list(self.workers.items()):
            if worker.isRunning():
                worker.stop()
                worker.wait(2000)  # 최대 2초 대기
            worker.deleteLater()
        self.workers.clear()
        event.accept()
