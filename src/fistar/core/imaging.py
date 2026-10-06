from pathlib import Path
import hashlib
import math
import numpy as np
import tifffile
from .models import Calibration, LoadedImage, Point

def load_tiff(path: Path) -> LoadedImage:
    path = Path(path).resolve()
    with tifffile.TiffFile(path) as f:
        if len(f.pages) != 1:
            raise ValueError("単一ページのTIFFを選択してください")
        page = f.pages[0]
        raw = page.asarray()
        if page.photometric.name not in ('MINISBLACK','MINISWHITE','RGB') or not (raw.ndim == 2 or raw.ndim == 3 and raw.shape[2] == 3):
            raise ValueError("グレースケールまたはRGBのTIFFが必要です")
        if raw.dtype.kind not in 'uif' or not np.isfinite(raw).all():
            raise ValueError("画像の画素値が不正です")
        if raw.size == 0:
            raise ValueError("画像に画素がありません")
        photometric = page.photometric.name
        calibration = None
        try:
            unit = int(page.tags['ResolutionUnit'].value)
            factor = {2:25.4, 3:10.0}[unit]
            def spacing(name):
                numerator, denominator = page.tags[name].value
                return factor * denominator / numerator
            calibration = Calibration(spacing('XResolution'), spacing('YResolution'), 'TIFF')
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            pass
    raw.setflags(write=False)
    return LoadedImage(path, raw, hashlib.sha256(path.read_bytes()).hexdigest(), calibration, photometric)

def analysis_channel(image: LoadedImage, channel: str = 'luminance') -> np.ndarray:
    raw = image.raw.astype(np.float64)
    if raw.ndim == 2:
        return raw
    if channel == 'luminance':
        return raw @ np.array([.299,.587,.114])
    if channel not in ('R','G','B'):
        raise ValueError("不明な解析チャンネルです")
    return raw[:,:,('R','G','B').index(channel)].copy()

def display_image(values: np.ndarray, low: float, high: float) -> np.ndarray:
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    return np.clip((values-low)/(high-low)*255,0,255).astype(np.uint8)

def manual_calibration(start: Point, end: Point, length_mm: float) -> Calibration:
    distance = math.hypot(end.x-start.x,end.y-start.y)
    if not math.isfinite(distance) or distance <= 0 or not math.isfinite(length_mm) or length_mm <= 0:
        raise ValueError("異なる2点と正の既知長さを指定してください")
    return Calibration(length_mm/distance,length_mm/distance,'manual',(start,end,length_mm))
