import os
import time
import uuid
import requests
import subprocess
import re
import json
import yt_dlp
from models import JobConfig, VideoType
from PyQt6.QtCore import QThread, pyqtSignal


def resolve_yasya_url(page_url: str, status_callback=None) -> str:
    """yasyadong.tv 페이지 URL에서 세그먼트 베이스 URL을 자동 추출.
    Chrome을 headless로 열어 네트워크 요청과 페이지 소스를 분석한다.
    반환: 'https://yavidssgood.com/HASH/' 형태의 베이스 URL
    """
    import undetected_chromedriver as uc

    if status_callback:
        status_callback("Chrome 브라우저로 페이지 로딩 중...")

    options = uc.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = uc.Chrome(options=options)
    try:
        driver.get(page_url)
        time.sleep(10)

        if status_callback:
            status_callback("네트워크 요청에서 세그먼트 URL 탐색 중...")

        # 1) 네트워크 로그에서 segment URL 찾기
        logs = driver.get_log('performance')
        for entry in logs:
            try:
                msg = json.loads(entry['message'])['message']
                if msg['method'] == 'Network.requestWillBeSent':
                    url = msg['params']['request']['url']
                    m = re.match(r'(https?://[^/]+/[A-Za-z0-9]+/)segment_\d+\.jpg', url)
                    if m:
                        return m.group(1)
            except Exception:
                pass

        # 2) 페이지 소스에서 items1.shtml 패턴으로 베이스 URL 추출
        source = driver.page_source
        m = re.search(r'(https?://[^/]+/[A-Za-z0-9]+/)items\d*\.shtml', source)
        if m:
            return m.group(1)

        raise RuntimeError("세그먼트 URL을 찾지 못했습니다. 페이지를 확인하세요.")
    finally:
        driver.quit()


class DownloadWorker(QThread):
    """QThread 기반 다운로드 워커 - 스레드 안전한 시그널 emit"""

    # 진행 상황, 상태 메시지, 완료 신호를 UI로 보냄
    progress = pyqtSignal(int, int)   # (세그먼트 번호, 마지막 세그먼트 크기)
    status   = pyqtSignal(str)        # 상태 메시지
    done     = pyqtSignal(bool, str)  # 완료 여부, 메시지

    def __init__(self, cfg: JobConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._stop = False
        self._out_ts = None  # 임시 파일 경로 추적용

    def stop(self):
        """외부(UI)에서 호출하면 루프가 멈춤"""
        self._stop = True

    def _normalize_url(self, u: str) -> str:
        """URL 끝에 '/'가 없으면 붙여줌"""
        return u if u.endswith('/') else u + '/'

    def _cleanup_temp_file(self):
        """임시 TS 파일 삭제"""
        if self._out_ts and os.path.exists(self._out_ts):
            try:
                os.remove(self._out_ts)
            except OSError:
                pass  # 삭제 실패해도 무시

    def _probe_segment(self, session: requests.Session, base: str, num: int, headers: dict) -> bool:
        """세그먼트가 존재하는지 HEAD 요청으로 확인 (빠른 탐지)"""
        url = f"{base}{str(num).zfill(self.cfg.zero_pad)}.jpg"
        try:
            # HEAD 요청으로 빠르게 확인 (본문 다운로드 안함)
            r = session.head(url, headers=headers, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                return True
            # HEAD가 지원 안되면 GET으로 재시도
            if r.status_code == 405:
                r = session.get(url, headers=headers, timeout=10, stream=True)
                return r.status_code == 200
            return False
        except:
            return False

    def _find_start(self, session: requests.Session, base: str, headers: dict) -> int:
        """시작 번호 자동 탐지 (0부터 순차 탐색)"""
        self.status.emit("시작 번호 탐지 중...")

        # 일반적인 시작 번호들 우선 확인 (0, 1)
        for start_candidate in [0, 1]:
            if self._stop:
                return 1
            if self._probe_segment(session, base, start_candidate, headers):
                self.status.emit(f"시작 번호 발견: {start_candidate}")
                return start_candidate

        # 못 찾으면 기본값 1 반환
        return 1

    def _find_end(self, session: requests.Session, base: str, headers: dict, start: int) -> int:
        """끝 번호 자동 탐지 (이진 탐색)"""
        self.status.emit("끝 번호 탐지 중...")

        # 1단계: 상한선 찾기 (지수적 증가)
        probe = start
        step = 100
        max_probe = 100000  # 최대 탐색 범위

        while probe < max_probe:
            if self._stop:
                return None
            if not self._probe_segment(session, base, probe, headers):
                break
            probe += step
            step = min(step * 2, 1000)  # 점점 큰 스텝으로

        # 2단계: 이진 탐색으로 정확한 끝 찾기
        low = start
        high = min(probe, max_probe)

        while low < high:
            if self._stop:
                return None
            mid = (low + high + 1) // 2
            if self._probe_segment(session, base, mid, headers):
                low = mid
            else:
                high = mid - 1

        self.status.emit(f"끝 번호 발견: {low}")
        return low

    def run(self):
        """다운로드 실행 (QThread.run 오버라이드)"""
        out_ts = None
        out_mp4 = None

        try:
            # yasyadong.tv 페이지 URL이면 세그먼트 URL 자동 추출
            url = self.cfg.base_folder_url.strip()
            if 'yasyadong' in url and ('_Action=items' in url or 'items_id' in url):
                try:
                    resolved = resolve_yasya_url(url, status_callback=lambda msg: self.status.emit(msg))
                    self.status.emit(f"세그먼트 URL 발견: {resolved}")
                    url = resolved
                except Exception as e:
                    self.done.emit(False, f"URL 추출 실패: {e}")
                    return

            # segment_0001.jpg 같은 형태로 URL 조합
            base = self._normalize_url(url) + "segment_"
            session = requests.Session()
            headers = self.cfg.headers or {}
            out_dir = self.cfg.save_dir or os.getcwd()

            # 자동 탐지 모드
            start = self.cfg.start
            end = self.cfg.end

            if self.cfg.auto_detect:
                # 시작번호 자동 탐지
                start = self._find_start(session, base, headers)
                if self._stop:
                    self.done.emit(False, "사용자에 의해 중단됨")
                    return

                # 끝번호 자동 탐지
                end = self._find_end(session, base, headers, start)
                if self._stop:
                    self.done.emit(False, "사용자에 의해 중단됨")
                    return

                if end is None or end < start:
                    self.done.emit(False, "유효한 세그먼트를 찾지 못했습니다. URL을 확인하세요.")
                    return

                self.status.emit(f"탐지 완료: {start} ~ {end} (총 {end - start + 1}개)")

            # 랜덤 고유 ID를 붙여 동일 out_name 입력 시 덮어쓰기 방지
            unique_id = uuid.uuid4().hex[:6]
            base_name, ext = os.path.splitext(self.cfg.out_name or "output.mp4")
            if not ext:
                ext = ".mp4"

            # 임시 TS 파일 및 최종 출력 파일 경로
            out_ts = os.path.join(out_dir, f"{base_name}_{unique_id}.ts")
            out_mp4 = os.path.join(out_dir, f"{base_name}_{unique_id}{ext}")
            self._out_ts = out_ts  # 정리용으로 저장

            # 기존에 남아있던 같은 이름 TS 삭제 (충돌 방지)
            if os.path.exists(out_ts):
                os.remove(out_ts)

            n404 = 0
            total_written = 0
            i = start
            total_segments = (end - start + 1) if end else None
            self.status.emit("다운로드 시작")

            # TS 병합 파일을 열어둠
            with open(out_ts, "ab") as merged:
                while not self._stop:
                    # end 값이 있으면 해당 번호까지 다운로드
                    if end is not None and i > end:
                        break

                    num = str(i).zfill(self.cfg.zero_pad)
                    url = f"{base}{num}.jpg"
                    ok = False
                    last_size = 0

                    # 재시도 루프
                    for attempt in range(1, self.cfg.retry + 1):
                        try:
                            with session.get(url, headers=headers, timeout=self.cfg.timeout, stream=True) as r:
                                if r.status_code == 404:
                                    ok = False
                                    break
                                r.raise_for_status()
                                blob = r.content
                                # TS 파일은 항상 0x47로 시작 → 아니면 잘못된 데이터
                                if not blob or blob[0] != 0x47:
                                    raise RuntimeError("Bad segment (not TS header 0x47)")
                                # 세그먼트 이어쓰기
                                merged.write(blob)
                                last_size = len(blob)
                                total_written += last_size
                                ok = True
                                break
                        except Exception as e:
                            if attempt == self.cfg.retry:
                                self.status.emit(f"{num} 다운로드 실패: {e}")
                            else:
                                time.sleep(1.0 * attempt)

                    if not ok:
                        n404 += 1
                        # 자동 탐지 모드에서는 404 허용치를 낮춤 (이미 범위를 알고 있으므로)
                        threshold = 3 if self.cfg.auto_detect and end else self.cfg.stop_after_n_404
                        if end is None and n404 >= threshold:
                            self.status.emit("연속 404 임계치 도달 → 종료")
                            break
                    else:
                        n404 = 0
                        self.progress.emit(i, last_size)

                    i += 1

            # 중지 요청으로 종료된 경우
            if self._stop:
                self._cleanup_temp_file()
                self.done.emit(False, "사용자에 의해 중단됨")
                return

            # 총 데이터가 하나도 없으면 실패 처리
            if total_written == 0:
                self._cleanup_temp_file()
                self.done.emit(False, "세그먼트를 하나도 받지 못했습니다. URL/헤더/쿠키를 확인하세요.")
                return

            # ffmpeg 실행해서 TS를 MP4 컨테이너로 변환
            self.status.emit("ffmpeg 컨테이너 변환 중…")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", out_ts, "-c", "copy", out_mp4],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                # 성공 시 임시 파일 삭제
                self._cleanup_temp_file()
                self.done.emit(True, out_mp4)
            except FileNotFoundError:
                # ffmpeg 없는 경우 - TS 파일 유지
                self.done.emit(False, f"ffmpeg가 없어 merged.ts만 생성했습니다: {out_ts}")
            except subprocess.CalledProcessError as e:
                self.done.emit(False, f"ffmpeg 오류: {e}")

        except Exception as e:
            # 전체 루프에서 예외 발생 시 정리 후 실패 신호
            self._cleanup_temp_file()
            self.done.emit(False, f"오류: {e}")


class PornhubDownloadWorker(QThread):
    """Pornhub 비디오 다운로드 워커 (yt-dlp 사용)"""

    progress = pyqtSignal(int, int)   # (다운로드 바이트, 전체 바이트)
    status   = pyqtSignal(str)        # 상태 메시지
    done     = pyqtSignal(bool, str)  # 완료 여부, 메시지

    def __init__(self, cfg: JobConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._stop = False
        self._downloaded_bytes = 0
        self._total_bytes = 0

    def stop(self):
        """외부(UI)에서 호출하면 루프가 멈춤"""
        self._stop = True

    def _progress_hook(self, d):
        """yt-dlp 진행 상황 콜백"""
        if self._stop:
            raise Exception("사용자에 의해 중단됨")

        if d['status'] == 'downloading':
            self._downloaded_bytes = d.get('downloaded_bytes', 0)
            self._total_bytes = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            self.progress.emit(self._downloaded_bytes, self._total_bytes)

        elif d['status'] == 'finished':
            self.status.emit("다운로드 완료, 처리 중...")

    def run(self):
        """다운로드 실행"""
        out_path = None
        try:
            url = self.cfg.base_folder_url.strip()

            # 출력 디렉토리 생성
            out_dir = self.cfg.save_dir or os.getcwd()
            os.makedirs(out_dir, exist_ok=True)

            # 고유 ID로 파일명 생성
            unique_id = uuid.uuid4().hex[:6]
            base_name, ext = os.path.splitext(self.cfg.out_name or "output.mp4")
            if not ext:
                ext = ".mp4"
            out_path = os.path.join(out_dir, f"{base_name}_{unique_id}{ext}")

            self.status.emit("비디오 정보 가져오는 중...")

            # yt-dlp 옵션 설정
            ydl_opts = {
                'format': 'worst[ext=mp4]/worst',  # 가장 낮은 화질로 테스트 (다운로드 속도 최대화)
                'outtmpl': out_path,
                'progress_hooks': [self._progress_hook],
                'quiet': False,  # 디버깅을 위해 로그 출력
                'no_warnings': False,
                'nocheckcertificate': True,
                # 타임아웃 및 재시도 설정
                'socket_timeout': 120,  # 소켓 타임아웃 더 증가
                'retries': 20,  # 재시도 횟수 더 증가
                'fragment_retries': 20,  # 프래그먼트 재시도
                'file_access_retries': 10,  # 파일 접근 재시도
                # HTTP 청크 크기 설정 (작은 청크로 타임아웃 방지)
                'http_chunk_size': 524288,  # 512KB 청크 (더 작게)
                # 버퍼 크기 설정
                'buffersize': 1024,
                # 사용자 정의 헤더가 있으면 사용
                'http_headers': self.cfg.headers if self.cfg.headers else {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                }
            }

            # 브라우저 쿠키 사용 시도 (에러 무시)
            try:
                ydl_opts['cookiesfrombrowser'] = ('chrome',)
            except:
                pass

            self.status.emit("비디오 다운로드 중...")

            # yt-dlp로 다운로드
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # 다운로드 완료
            if os.path.exists(out_path):
                self.done.emit(True, out_path)
            else:
                self.done.emit(False, "다운로드는 완료되었으나 파일을 찾을 수 없습니다.")

        except Exception as e:
            if self._stop:
                self.done.emit(False, "사용자에 의해 중단됨")
            else:
                self.done.emit(False, f"오류: {e}")

            # 실패 시 부분 다운로드 파일 삭제
            if out_path and os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except:
                    pass
