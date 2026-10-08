import math
from .models import *
from .geometry import minimax_circle, physical_line, intersection_centroid

def evaluate_spokes(spokes: tuple[Spoke,...], laser: Point, calibration: Calibration | None) -> AnalysisResult:
    if not all(math.isfinite(v) for v in (laser.x,laser.y)):
        raise ValueError("レーザー点が不正です")
    active = tuple(s for s in spokes if not s.excluded)
    def metric(lines, point, unit):
        circle = minimax_circle(lines)
        delta = Point(circle.center.x-point.x,point.y-circle.center.y)
        return MetricResult(unit,circle,delta,math.hypot(delta.x,delta.y))
    pixels = metric(tuple(s.line for s in active),laser,'px')
    physical = None
    if calibration:
        physical = metric(tuple(physical_line(s.line,calibration) for s in active),
                          Point(laser.x*calibration.sx_mm,laser.y*calibration.sy_mm),'mm')
    cp,cm,error=evaluate_centroids(active,laser,calibration)
    return AnalysisResult(pixels,physical,tuple(s.id for s in active),cp,cm,error)


def evaluate_centroids(spokes,laser,calibration):
    active=tuple(s for s in spokes if not s.excluded)
    cp=cm=None; error=''
    try:
        cp=intersection_centroid(active,laser,'px')
        if calibration:
            from dataclasses import replace
            cm=intersection_centroid(tuple(replace(s,line=physical_line(s.line,calibration)) for s in active),
                Point(laser.x*calibration.sx_mm,laser.y*calibration.sy_mm),'mm')
    except (ValueError,OverflowError) as e:
        cp=cm=None; error=str(e)
    return cp,cm,error

def judge(result: MetricResult, limits: Limits) -> Judgment:
    def status(value, limit):
        if limit is None: return 'unset'
        if limits.unit != result.unit: return 'unit_mismatch'
        return 'within' if value <= limit else 'exceeded'
    return Judgment(status(result.circle.radius,limits.radius),status(result.laser_distance,limits.laser_distance))
