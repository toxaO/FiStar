from dataclasses import dataclass
from pathlib import Path
import math
import numpy as np

@dataclass(frozen=True)
class Point:
    x: float
    y: float

@dataclass(frozen=True)
class Line:
    nx: float
    ny: float
    offset: float
    def __post_init__(self):
        norm = math.hypot(self.nx, self.ny)
        if not math.isfinite(norm) or norm == 0 or not math.isfinite(self.offset):
            raise ValueError("中心線の係数が不正です")
        norm = 1.0 if abs(norm-1.0) < 1e-15 else norm
        object.__setattr__(self, 'nx', self.nx / norm)
        object.__setattr__(self, 'ny', self.ny / norm)
        object.__setattr__(self, 'offset', self.offset / norm)

@dataclass(frozen=True)
class Calibration:
    sx_mm: float
    sy_mm: float
    source: str
    reference: tuple[Point, Point, float] | None = None
    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (self.sx_mm,self.sy_mm)):
            raise ValueError("校正値は正の有限値が必要です")

@dataclass(frozen=True)
class LoadedImage:
    path: Path
    raw: np.ndarray
    sha256: str
    tagged_calibration: Calibration | None
    photometric: str = 'MINISBLACK'

@dataclass(frozen=True)
class DetectionSettings:
    radius_ratio: float = .85
    min_peak_height: float = .25
    polarity: str = 'dark'
    def __post_init__(self):
        if not math.isfinite(self.radius_ratio) or not .05 <= self.radius_ratio <= .95:
            raise ValueError('探索円の半径は5〜95%で指定してください')
        if not math.isfinite(self.min_peak_height) or not 0 < self.min_peak_height < 1:
            raise ValueError('最小ピーク高さは0%より大きく100%未満で指定してください')
        if self.polarity not in ('dark','bright'):
            raise ValueError('帯の極性が不正です')

@dataclass(frozen=True)
class Spoke:
    id: str
    line: Line
    support: tuple[Point, ...] = ()
    origin: str = 'auto'
    excluded: bool = False

@dataclass(frozen=True)
class DetectionResult:
    spokes: tuple[Spoke, ...]
    settings: DetectionSettings | dict
    warnings: tuple[str, ...] = ()
    method: str = 'manual'
    pylinac_version: str | None = None
    points: tuple[Point, ...] = ()
    search_center: Point | None = None
    radius_px: float | None = None

@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float

@dataclass(frozen=True)
class MetricResult:
    unit: str
    circle: Circle
    laser_delta: Point
    laser_distance: float

@dataclass(frozen=True)
class Intersection:
    spoke_ids: tuple[str, str]
    point: Point
    distance: float

@dataclass(frozen=True)
class CentroidMetric:
    unit: str
    center: Point
    laser_delta: Point
    laser_distance: float
    intersections: tuple[Intersection, ...]
    max_distance: float
    skipped_pairs: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class AnalysisResult:
    pixels: MetricResult
    physical: MetricResult | None
    active_spoke_ids: tuple[str, ...]
    centroid_pixels: CentroidMetric | None = None
    centroid_physical: CentroidMetric | None = None
    centroid_error: str = ''
    center_method: str = 'minimax'
    @property
    def primary(self):
        return self.physical or self.pixels
    @property
    def selected(self):
        if self.center_method=='intersection_centroid':
            return self.centroid_physical or self.centroid_pixels
        return self.primary

@dataclass(frozen=True)
class Limits:
    unit: str = 'mm'
    radius: float | None = None
    laser_distance: float | None = None
    def __post_init__(self):
        if self.unit not in ('px','mm') or any(v is not None and (not math.isfinite(v) or v < 0) for v in (self.radius,self.laser_distance)):
            raise ValueError("許容値の単位・数値が不正です")

@dataclass(frozen=True)
class Judgment:
    radius: str
    laser_distance: str

@dataclass(frozen=True)
class Measurement:
    id: str
    created_at: str
    device: str
    axis: str
    image_name: str
    result: AnalysisResult
    limits: Limits
    judgment: Judgment
    snapshot: dict
