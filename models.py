from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum

class VideoType(Enum):
    YASYA = "yasya"
    PORNHUB = "pornhub"

@dataclass
class JobConfig:
    base_folder_url: str
    save_dir: str
    out_name: str
    video_type: VideoType = VideoType.YASYA
    start: int = 1
    zero_pad: int = 4
    end: Optional[int] = None
    stop_after_n_404: int = 10
    retry: int = 5
    timeout: int = 30
    headers: Optional[Dict[str, str]] = None
    auto_detect: bool = True  # 시작/끝번호 자동 탐지 여부
