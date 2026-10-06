from math import sqrt
import numpy as np
import pytest
from fistar.core.models import Line
from fistar.core.geometry import minimax_circle, fit_line

def test_triangle():
    c = minimax_circle((Line(1,0,0),Line(0,1,0),Line(1,1,2)))
    r = 2/(2+sqrt(2))
    assert (c.center.x,c.center.y,c.radius) == pytest.approx((r,r,r),abs=1e-6)

def test_negative_concurrent():
    c = minimax_circle((Line(1,0,-2),Line(0,1,-3),Line(1,1,-5)))
    assert (c.center.x,c.center.y,c.radius) == pytest.approx((-2,-3,0),abs=1e-6)

def test_nonunique_tiebreak():
    c = minimax_circle((Line(1,0,-1),Line(1,0,1),Line(0,1,0),Line(1,1,0)))
    assert (c.center.x,c.center.y,c.radius) == pytest.approx((0,0,1),abs=1e-6)

@pytest.mark.parametrize('lines', [(Line(1,0,0),)*3,(Line(1,0,0),Line(0,1,0))])
def test_insufficient_directions(lines):
    with pytest.raises(ValueError): minimax_circle(lines)

def test_tls_vertical():
    line = fit_line(np.array([[2,0],[2,5],[2,10]]))
    assert abs(line.nx*2-line.offset) < 1e-6


def test_four_common_lines_at_positive_coordinates():
    from fistar.core.models import Line
    from fistar.core.geometry import minimax_circle
    circle=minimax_circle((Line(1,0,32),Line(0,1,32),Line(1,1,64),Line(1,-1,0)))
    assert abs(circle.center.x-32)<1e-10 and abs(circle.center.y-32)<1e-10
    assert circle.radius<1e-10
