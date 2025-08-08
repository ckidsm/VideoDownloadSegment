# pip install requests tqdm
import os
import sys
import time
import requests
from tqdm import tqdm
from subprocess import run, CalledProcessError

BASE = "https://yavidssgood.com/7785931F5EB649BO875EE5EBCF78C978/segment_"
START = 1
END = 1024          # 몰라서 자동으로 멈추고 싶으면 None 로 두고, 404가 연속으로 n번 나올 때 stop
ZEROPAD = 4         # 0001 형식
OUT_TS = "merged.ts"
OUT_MP4 = "output.mp4"
RETRY = 3
TIMEOUT = 30
STOP_AFTER_N_404 = 5

# HLS가 UA/Referer 요구할 수 있으니 필요 시 수정
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://yavidssgood.com/",
}

def download_segment(i: int, session: requests.Session) -> bytes:
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
            time.sleep(1.0 * attempt)  # 점진 백오프
    return None

def main():
    session = requests.Session()
    n404 = 0
    total_written = 0

    # 기존 병합 파일 있으면 지움
    if os.path.exists(OUT_TS):
        os.remove(OUT_TS)

    # 파일에 바로 이어쓰기(= cat 효과)
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
                    # 연속 404 n번 → 끝났다고 판단
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

    # ffmpeg로 mp4 컨테이너만 교체 (재인코딩 없음)
    try:
        print("[*] ffmpeg 컨테이너 변환 중…")
        run(
            ["ffmpeg", "-y", "-i", OUT_TS, "-c", "copy", OUT_MP4],
            check=True
        )
        print(f"완료: {OUT_MP4}")
    except FileNotFoundError:
        print("ffmpeg가 없습니다. 설치 후 다시 실행하세요.")
        return 1
    except CalledProcessError as e:
        print(f"ffmpeg 오류: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
