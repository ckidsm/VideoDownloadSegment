import re

# 허용되는 헤더 키 패턴 (보안상 위험한 헤더 차단)
ALLOWED_HEADER_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9\-]*$')

# 차단할 헤더 (소문자로 비교)
BLOCKED_HEADERS = {
    'host',           # 요청 대상 조작 방지
    'content-length', # 자동 계산되어야 함
    'transfer-encoding',
    'connection',
    'upgrade',
}


def parse_headers_text(text: str) -> dict:
    """
    사용자 입력 헤더 텍스트를 딕셔너리로 파싱

    - 빈 키/값 검증
    - 위험한 헤더 차단
    - 유니코드 문자 정제
    """
    text = (text or "").strip()
    if not text:
        # 기본 헤더 반환
        return {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.yasyadong.cc",
            "Origin": "https://www.yasyadong.cc",
            "Accept": "*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,ja;q=0.8,en;q=0.7",
        }

    hdrs = {}
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            continue

        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()

        # 빈 키 검증
        if not k:
            raise ValueError(f"줄 {line_num}: 헤더 키가 비어있습니다")

        # 헤더 키 형식 검증
        if not ALLOWED_HEADER_PATTERN.match(k):
            raise ValueError(f"줄 {line_num}: 잘못된 헤더 키 형식 '{k}'")

        # 차단된 헤더 검사
        if k.lower() in BLOCKED_HEADERS:
            raise ValueError(f"줄 {line_num}: '{k}' 헤더는 보안상 설정할 수 없습니다")

        # 빈 값은 허용 (일부 헤더는 빈 값이 유효할 수 있음)
        # 유니코드 들어오면 라틴-1로 표현 가능한 범위만 남김
        v = v.replace("…", "...").replace(""", "\"").replace(""", "\"")
        v = v.replace("'", "'").replace("'", "'")
        v = v.encode("latin-1", "ignore").decode("latin-1")

        hdrs[k] = v

    return hdrs
