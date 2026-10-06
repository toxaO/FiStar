"""Approved v1 regression checks replace the legacy ray-count/intersection-average assumptions."""
import pytest
from fistar.core.analysis import evaluate_spokes
from fistar.core.models import Point,Spoke,Line

def test_laser_does_not_change_minimax_center():
    spokes=tuple(Spoke(str(i),line) for i,line in enumerate((Line(1,0,0),Line(0,1,0),Line(1,1,2))))
    a=evaluate_spokes(spokes,Point(0,0),None)
    b=evaluate_spokes(spokes,Point(100,100),None)
    assert a.pixels.circle==b.pixels.circle
    assert a.pixels.laser_distance!=b.pixels.laser_distance
