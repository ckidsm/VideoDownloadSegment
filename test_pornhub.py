#!/usr/bin/env python3
"""Pornhub 다운로드 테스트 스크립트"""
import sys
import os
from models import JobConfig, VideoType
from workers import PornhubDownloadWorker
from PyQt6.QtCore import QCoreApplication

def test_pornhub_download(url: str):
    """Pornhub 비디오 다운로드 테스트"""
    print(f"\n테스트 시작: {url}")
    print("=" * 60)

    # Qt 애플리케이션 (시그널 처리를 위해 필요)
    app = QCoreApplication(sys.argv)

    # 설정
    cfg = JobConfig(
        base_folder_url=url,
        save_dir="save",
        out_name="test_pornhub.mp4",
        video_type=VideoType.PORNHUB,
    )

    # 워커 생성
    worker = PornhubDownloadWorker(cfg)

    # 시그널 연결
    def on_progress(downloaded, total):
        if total > 0:
            percent = int((downloaded / total) * 100)
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            print(f"\r진행: {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)
        else:
            downloaded_mb = downloaded / (1024 * 1024)
            print(f"\r다운로드: {downloaded_mb:.1f} MB", end='', flush=True)

    def on_status(msg):
        print(f"\n상태: {msg}")

    def on_done(success, message):
        print(f"\n\n결과: {'성공' if success else '실패'}")
        print(f"메시지: {message}")
        print("=" * 60)
        app.quit()

    worker.progress.connect(on_progress)
    worker.status.connect(on_status)
    worker.done.connect(on_done)

    # 워커 시작
    worker.start()

    # 이벤트 루프 실행
    sys.exit(app.exec())

if __name__ == "__main__":
    # 테스트 URL - 사용자가 제공한 새 URL (제대로 된 영상)
    test_url = "https://www.pornhub.com/view_video.php?viewkey=6896a4835f002"

    print("Pornhub 다운로드 테스트")
    print(f"URL 테스트를 시작합니다: {test_url}")

    # 새 URL로 테스트
    test_pornhub_download(test_url)
