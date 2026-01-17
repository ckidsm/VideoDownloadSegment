# pip install requests tqdm
import os                 # 파일/디렉토리 작업용
import sys                # 표준 입출력, 예외 출력 등
import time               # 재시도 시 지연(대기) 처리용
import requests           # HTTP 요청 라이브러리
from tqdm import tqdm     # 진행 상황(progress bar) 표시
from subprocess import run, CalledProcessError  # ffmpeg 실행용

# ===================== 사용자 설정 =====================
# BASE URL 예시들 (필요 시 직접 선택/수정)
# BASE = "https://yavidssgood.com/7785931F5EB649B0875EE5EBCF78C978/segment_"
# BASE = "https://yavidssgood.com/E62ABBC3933049BF97EA1A59897FBC8A/segment_"
# BASE = "https://yavidssgood.com/9E6C1F2D40834F11B682BC9BF09CB1EE/segment_"
# BASE = "https://yavidssgood.com/239D9DB6BDDC42E2953961B3DD5DF600/segment_"
# BASE = "https://yavidssgood.com/546D51A2B380427786ED2022ACE2D9D5/segment_"
# BASE = "https://yavidssgood.com/1FF5CE6E148548649F4962F41A6E89F1/segment_"

Segment = "segment_"  # 세그먼트 접두사 (파일명 앞부분)
# url 예시 (폴더 URL, 뒤에 segment_xxxx.jpg 붙음)
# url = "https://yavidssgood.com/1FF5CE6E148548649F4962F41A6E89F1/"
# url = "https://yavidssgood.com/758B71DD86A1418F814FA90BA997AA13/"
url = "https://yavidssgood.com/068E1833C4084E17A68F0C0ECA25E36E/"

# 실제 다운로드 대상 URL 접두부
BASE = url + Segment

START = 1          # 시작 번호
END = None         # 끝 번호 (None → 모를 때, 404 연속 감지 시 종료)
ZEROPAD = 4        # 파일명 자릿수 (0001 형식)
OUT_TS = "merged.ts"   # 중간 TS 병합 파일명
OUT_MP4 = "output.mp4" # 최종 출력 mp4 파일명
RETRY = 3              # 다운로드 재시도 횟수
TIMEOUT = 30           # HTTP 요청 타임아웃(초)
STOP_AFTER_N_404 = 5   # 연속 404가 몇 번 나오면 종료할지

# 실제 브라우저 요청 헤더 (DevTools → Request Headers에서 복사 가능)
# Cookie 필요 시 아래 주석 해제 후 값 넣어야 함
HEADERS = {
    "User-Agent": "...",   # UA 문자열 (크롬 등 브라우저와 동일하게)
    "Referer": "https://www.yasyadong.cc",   # 참조 URL
    "Origin": "https://www.yasyadong.cc",    # Origin 헤더
    "Accept": "*/*",                          # 모든 타입 허용
    "Accept-Language": "ko-KR,ko;q=0.9,ja;q=0.8,en;q=0.7"  # 언어 우선순위
}
# =======================================================


def download_segment(i: int, session: requests.Session) -> bytes:
    """단일 세그먼트를 다운로드하여 바이트 데이터를 반환"""
    num = str(i).zfill(ZEROPAD)      # 4자리 형식(예: 0001)
    url = f"{BASE}{num}.jpg"         # 최종 세그먼트 URL
    for attempt in range(1, RETRY + 1):   # 재시도 루프
        try:
            # GET 요청 (stream=True: 큰 파일 대비)
            with session.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True) as r:
                if r.status_code == 404:  # 파일 없음 → None 반환
                    return None
                r.raise_for_status()      # 다른 오류 발생 시 예외 발생
                return r.content          # 정상 → 바이트 데이터 반환
        except Exception as e:
            # 재시도 횟수 도달 시 마지막 예외 발생
            if attempt == RETRY:
                raise
            # 점진적 대기 (1초, 2초, 3초 …)
            time.sleep(1.0 * attempt)
    return None  # 안전용 반환


def main():
    session = requests.Session()  # 세션 생성(연결 재사용)
    n404 = 0                      # 연속 404 카운터
    total_written = 0             # 총 다운로드된 바이트 수

    # 기존 병합 TS 파일 삭제 (있으면 덮어쓰기)
    if os.path.exists(OUT_TS):
        os.remove(OUT_TS)

    # 세그먼트 순차 다운로드 & 파일 병합 (ab 모드: 이어쓰기)
    with open(OUT_TS, "ab") as merged, tqdm(unit="seg") as bar:
        i = START
        while True:
            # 끝 번호가 정해져 있고, 이미 넘었다면 종료
            if END is not None and i > END:
                break

            try:
                blob = download_segment(i, session)  # 세그먼트 다운로드
            except Exception as e:
                # 다운로드 자체 실패 시 에러 출력 후 종료
                print(f"[!] {i:0{ZEROPAD}} 다운로드 실패: {e}", file=sys.stderr)
                return 1

            if blob is None:
                # 세그먼트 없음 (404)
                n404 += 1
                if END is None and n404 >= STOP_AFTER_N_404:
                    # 끝 번호 모름 + 연속 404 일정 횟수 → 종료
                    break
            else:
                # 정상 세그먼트 받음
                n404 = 0
                merged.write(blob)              # 파일에 이어쓰기
                total_written += len(blob)      # 총량 누적
                # 진행바 업데이트
                bar.set_postfix(idx=i, size=f"{len(blob)/1024:.0f}KB")
                bar.update(1)

            i += 1  # 다음 세그먼트 번호로 진행

    # 하나도 못 받았다면 에러 메시지 출력
    if total_written == 0:
        print("아무 세그먼트도 받지 못했습니다. BASE/헤더/범위를 확인하세요.")
        return 1

    # ffmpeg로 mp4 컨테이너 변환 (재인코딩 없음, 단순 copy)
    try:
        print("[*] ffmpeg 컨테이너 변환 중…")
        run(
            ["ffmpeg", "-y", "-i", OUT_TS, "-c", "copy", OUT_MP4],  # TS → MP4
            check=True
        )
        print(f"[완료] {OUT_MP4}")
    except FileNotFoundError:
        # ffmpeg 설치 안 됨
        print("[에러] ffmpeg가 설치되어 있지 않습니다. 설치 후 다시 실행하세요.")
        return 1
    except CalledProcessError as e:
        # ffmpeg 실행 중 에러
        print(f"[ffmpeg 오류] {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    # main() 실행 후 반환 코드로 프로그램 종료
    raise SystemExit(main())
