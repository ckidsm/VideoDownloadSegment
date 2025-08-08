# pip install requests tqdm
import os
import sys
import time
import requests
from tqdm import tqdm
from subprocess import run, CalledProcessError

# ===================== 사용자 설정 =====================
BASE = "https://yavidssgood.com/7785931F5EB649B0875EE5EBCF78C978/segment_"
START = 1
END = 1024          # None으로 두면 404 연속 발생 시 멈춤
ZEROPAD = 4         # 파일명 자리수 (0001 형식)
OUT_TS = "merged.ts"
OUT_MP4 = "output.mp4"
RETRY = 3
TIMEOUT = 30
STOP_AFTER_N_404 = 5

# 실제 브라우저 요청 헤더 (DevTools → Request Headers에서 그대로 복사)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Referer": "https://www.yasyadong.cc",
    "Origin": "https://www.yasyadong.cc",
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9,ja;q=0.8,en;q=0.7",
    "Cookie": "cf_clearance=abc123xyz456; PHPSESSID=xxxxxx; __ddg1_=yyyyyy"
}


# =======================================================

def download_segment(i: int, session: requests.Session) -> bytes:
    """단일 세그먼트 다운로드"""
    num = str(i).zfill(ZEROPAD)
    url = f"{BASE}{num}.jpg"
    for attempt in range(1, RETRY + 1):
        try:
            with session.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True) as r:
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.content
        except Exception as e:
            if attempt == RETRY:
                raise
            time.sleep(1.0 * attempt)  # 점진적 대기
    return None

def main():
    session = requests.Session()
    n404 = 0
    total_written = 0

    # 기존 병합 파일 삭제
    if os.path.exists(OUT_TS):
        os.remove(OUT_TS)

    # 세그먼트 순차 다운로드 & TS 파일 병합
    with open(OUT_TS, "ab") as merged, tqdm(unit="seg") as bar:
        i = START
        while True:
            if END is not None and i > END:
                break

            try:
                blob = download_segment(i, session)
            except Exception as e:
                print(f"[!] {i:0{ZEROPAD}} 다운로드 실패: {e}", file=sys.stderr)
                return 1

            if blob is None:
                n404 += 1
                if END is None and n404 >= STOP_AFTER_N_404:
                    break
            else:
                n404 = 0
                merged.write(blob)
                total_written += len(blob)
                bar.set_postfix(idx=i, size=f"{len(blob)/1024:.0f}KB")
                bar.update(1)

            i += 1

    if total_written == 0:
        print("아무 세그먼트도 받지 못했습니다. BASE/헤더/범위를 확인하세요.")
        return 1

    # ffmpeg로 mp4 컨테이너로 변환 (재인코딩 없음)
    try:
        print("[*] ffmpeg 컨테이너 변환 중…")
        run(
            ["ffmpeg", "-y", "-i", OUT_TS, "-c", "copy", OUT_MP4],
            check=True
        )
        print(f"[완료] {OUT_MP4}")
    except FileNotFoundError:
        print("[에러] ffmpeg가 설치되어 있지 않습니다. 설치 후 다시 실행하세요.")
        return 1
    except CalledProcessError as e:
        print(f"[ffmpeg 오류] {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
