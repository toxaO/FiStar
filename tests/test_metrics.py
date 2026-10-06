from math import sqrt
import pytest
from fistar.core.models import *
from fistar.core.analysis import evaluate_spokes, judge

def test_anisotropic_and_laser():
    spokes = tuple(Spoke(str(i),l) for i,l in enumerate((Line(1,0,0),Line(0,1,0),Line(1,1,2))))
    result = evaluate_spokes(spokes+(Spoke('excluded',Line(1,0,100),excluded=True),),Point(0,0),Calibration(2,1,'test'))
    r = 4/(3+sqrt(5))
    assert result.physical.circle.radius == pytest.approx(r,abs=1e-6)
    assert result.physical.laser_delta == Point(result.physical.circle.center.x,result.physical.circle.center.y)
    assert result.physical.laser_distance == pytest.approx(sqrt(2)*r,abs=1e-6)
    assert len(result.active_spoke_ids) == 3

def test_limits_unrounded_and_unit():
    m = MetricResult('mm',Circle(Point(0,0),1.00001),Point(0,0),2)
    assert judge(m,Limits('mm',1,2)) == Judgment('exceeded','within')
    assert judge(m,Limits()) == Judgment('unset','unset')
    assert judge(m,Limits('px',1,None)) == Judgment('unit_mismatch','unset')
