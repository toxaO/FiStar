"""Pylinacの円周FWHM検出をFiStarの中心線へ変換する。"""
import math
from uuid import uuid4
import numpy as np
from .models import DetectionSettings, DetectionResult, Point, Spoke
from .geometry import fit_line


def search_radius(shape: tuple[int, ...], hub: Point, settings: DetectionSettings) -> float:
    """Pylinac ArrayImage.dist2edge_minと同じ画像端の定義（px）。"""
    h, w = shape[:2]
    return min(h-hub.y, w-hub.x, hub.x, hub.y)*settings.radius_ratio


def detect_spokes(values: np.ndarray, hub: Point, settings: DetectionSettings) -> DetectionResult:
    # Load the analysis backend in the detection worker, not during GUI startup.
    from pylinac import __version__ as PYLINAC_VERSION
    from pylinac.core.geometry import Point as PylinacPoint
    from pylinac.core.image import ArrayImage
    from pylinac.starshot import StarProfile
    image = np.array(values, dtype=np.float64, copy=True)
    if image.ndim != 2 or image.size == 0 or not np.isfinite(image).all():
        raise ValueError('検出には有限値の2次元画像が必要です')
    h, w = image.shape
    if not all(math.isfinite(v) for v in (hub.x, hub.y)) or not (0 < hub.x < w and 0 < hub.y < h):
        raise ValueError('探索中心を画像の内側に指定してください')
    radius = search_radius(image.shape, hub, settings)
    if radius < 2:
        raise ValueError('探索円が小さすぎます。半径またはレーザー点を調整してください')
    if float(np.ptp(image)) == 0:
        raise ValueError('画像に照射帯を識別できる濃淡がありません')
    # Work on a copy: dark bands must become upward peaks for Pylinac.
    if settings.polarity == 'dark':
        image = image.max()-image
    image -= image.min()
    try:
        profile = StarProfile(ArrayImage(image), PylinacPoint(hub.x, hub.y),
                              settings.radius_ratio, settings.min_peak_height, fwhm=True)
    except (ValueError, IndexError, RuntimeError, FloatingPointError) as e:
        raise ValueError('円周プロファイルを抽出できません。探索半径・最小ピーク高さ・極性を調整してください') from e
    points = tuple(sorted((Point(float(p.x), float(p.y)) for p in profile.peaks),
                          key=lambda p: math.atan2(p.y-hub.y, p.x-hub.x)%(2*math.pi)))
    if len(points)%2:
        raise ValueError(f'検出点が奇数（{len(points)}点）です。両側の腕を検出できるよう条件を調整して再検出してください')
    if len(points) < 6:
        raise ValueError(f'検出点が不足（{len(points)}点）しています。自動検出には6点以上が必要です。条件を調整して再検出してください')
    if not all(math.isfinite(v) for p in points for v in (p.x,p.y)):
        raise ValueError('検出点の座標が不正です')
    # Pylinac LineManager uses the same half-count offset pairing.
    half = len(points)//2
    spokes = []
    for i in range(half):
        support = (points[i], points[i+half])
        line = fit_line(np.array([(p.x,p.y) for p in support]))
        spokes.append(Spoke(str(uuid4()), line, support))
    return DetectionResult(tuple(spokes), settings, (), 'pylinac-fwhm',
                           PYLINAC_VERSION, points, hub, float(profile.radius))
