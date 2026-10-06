import numpy as np
from scipy.optimize import linprog, minimize
from .models import Line, Point, Circle

def fit_line(points: np.ndarray) -> Line:
    p = np.asarray(points,dtype=float)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 2 or not np.isfinite(p).all():
        raise ValueError("中心線には有限値の2点以上が必要です")
    mean = p.mean(axis=0)
    _, s, vt = np.linalg.svd(p-mean,full_matrices=False)
    if s[0] <= 1e-12:
        raise ValueError("異なる点を指定してください")
    n = vt[-1]
    return Line(float(n[0]),float(n[1]),float(n@mean))

def minimax_circle(lines: tuple[Line,...]) -> Circle:
    n = np.array([(l.nx,l.ny) for l in lines])
    original_b = np.array([l.offset for l in lines])
    directions = []
    for row in n:
        if not any(abs(row@v) > 1-1e-8 for v in directions):
            directions.append(row)
    if len(directions) < 3:
        raise ValueError("異なる方向の有効な中心線が3本以上必要です")
    origin = np.linalg.lstsq(n,original_b,rcond=None)[0]
    residual = original_b-n@origin
    # Normalize tiny residuals too: a fixed floor can put them below
    # the LP feasibility tolerance and make a subsequent tie-break infeasible.
    scale = float(np.max(np.abs(residual))) or 1.0
    b = residual/scale
    a = np.vstack((np.column_stack((n,-np.ones(len(n)))),np.column_stack((-n,-np.ones(len(n))))))
    solution = linprog([0,0,1],A_ub=a,b_ub=np.r_[b,-b],bounds=[(None,None),(None,None),(0,None)],method='highs')
    if not solution.success or not np.isfinite(solution.x).all():
        raise ValueError("最小円の計算に失敗しました")
    radius = max(0.,float(solution.x[2]))
    least = np.linalg.lstsq(n,b,rcond=None)[0]
    if np.max(np.abs(n@least-b)) <= radius + 1e-9:
        center = least
    else:
        constraints = {'type':'ineq','fun':lambda c: np.r_[radius+1e-10-(n@c-b),radius+1e-10+(n@c-b)],
                       'jac':lambda c: np.vstack((-n,n))}
        selected = minimize(lambda c: float(np.sum((n@c-b)**2)),solution.x[:2],
                            jac=lambda c: 2*n.T@(n@c-b),constraints=constraints,
                            method='SLSQP',options={'ftol':1e-12,'maxiter':500})
        if not selected.success:
            raise ValueError("最適中心の選択に失敗しました")
        center = selected.x
    if not np.isfinite(center).all() or np.max(np.abs(n@center-b)) > radius+1e-7:
        raise ValueError("円の制約を満たしません")
    center = origin+center*scale
    actual_radius = radius*scale
    if np.max(np.abs(n@center-original_b)) > actual_radius+1e-7:
        raise ValueError("元座標で円の制約を満たしません")
    return Circle(Point(float(center[0]),float(center[1])),actual_radius)

def physical_line(line: Line, calibration) -> Line:
    return Line(line.nx/calibration.sx_mm,line.ny/calibration.sy_mm,line.offset)


def intersection_centroid(spokes, laser: Point, unit: str):
    """All finite line-pair intersections, equally weighted; no outlier removal."""
    import math
    from itertools import combinations
    from .models import CentroidMetric, Intersection
    directions=[]
    for spoke in spokes:
        n=np.array((spoke.line.nx,spoke.line.ny))
        if not any(abs(n@v)>1-1e-8 for v in directions): directions.append(n)
    if len(directions)<3:
        raise ValueError('交点重心には異なる方向の中心線が3本以上必要です')
    points=[]; skipped=[]; warnings=[]
    for a,b in combinations(spokes,2):
        pair=(a.id,b.id); la,lb=a.line,b.line
        det=la.nx*lb.ny-la.ny*lb.nx
        if abs(det)<=1e-12:
            skipped.append(pair); continue
        if math.degrees(math.asin(min(1.,abs(det))))<1:
            warnings.append(f'帯ID {a.id} / {b.id}：線間角度1度未満。遠方交点により重心が不安定になる可能性があります')
        with np.errstate(over='ignore',invalid='ignore'):
            xy=np.linalg.solve([[la.nx,la.ny],[lb.nx,lb.ny]],[la.offset,lb.offset])
        if not np.isfinite(xy).all(): raise ValueError('交点が非有限値となり重心を計算できません')
        points.append((pair,Point(float(xy[0]),float(xy[1]))))
    if not points: raise ValueError('計算可能な交点がありません')
    # Divide before summing to avoid overflow of a finite mean.
    with np.errstate(over='ignore',invalid='ignore'):
        center=np.sum(np.array([(p.x,p.y) for _,p in points])/len(points),axis=0)
    c=Point(float(center[0]),float(center[1]))
    delta=Point(c.x-laser.x,c.y-laser.y)
    intersections=tuple(Intersection(pair,p,math.hypot(p.x-c.x,p.y-c.y)) for pair,p in points)
    distance=math.hypot(delta.x,delta.y); maximum=max(p.distance for p in intersections)
    if not all(math.isfinite(v) for v in (*center,delta.x,delta.y,distance,maximum)):
        raise ValueError('交点重心の計算結果が非有限値です')
    return CentroidMetric(unit,c,delta,distance,intersections,maximum,tuple(skipped),tuple(warnings))
