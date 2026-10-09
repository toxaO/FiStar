import math
from dataclasses import replace
import pytest
from fistar.core.models import Line,Point,Spoke,Calibration,Limits
from fistar.core.analysis import evaluate_spokes
from fistar.core.geometry import intersection_centroid


def spokes(*lines):
    return tuple(Spoke(str(i),line) for i,line in enumerate(lines))


def test_known_triangle_and_pair_distances():
    r=intersection_centroid(spokes(Line(1,0,0),Line(0,1,0),Line(1,1,2)),Point(0,0),'px')
    assert r.center.x==pytest.approx(2/3) and r.center.y==pytest.approx(2/3)
    assert len(r.intersections)==3 and r.max_distance==pytest.approx(math.sqrt(20)/3)
    assert r.intersections[0].spoke_ids==('0','1')


def test_parallel_and_far_points_are_retained():
    r=intersection_centroid(spokes(Line(1,0,0),Line(1,0,1),Line(0,1,0),Line(1,.001,2)),Point(0,0),'px')
    assert r.skipped_pairs==(('0','1'),)
    assert len(r.intersections)==5 and max(abs(p.point.y) for p in r.intersections)>1000
    assert r.warnings


def test_common_points_counted_by_pair():
    r=intersection_centroid(spokes(Line(1,0,2),Line(0,1,3),Line(1,1,5),Line(1,-1,-1)),Point(0,0),'px')
    assert len(r.intersections)==6
    assert r.center.x==pytest.approx(2) and r.center.y==pytest.approx(3)


def test_calibration_laser_and_exclusion():
    s=spokes(Line(1,0,0),Line(0,1,0),Line(1,1,2),Line(1,0,4))
    s=s[:3]+(replace(s[3],excluded=True),)
    a=evaluate_spokes(s,Point(0,0),Calibration(2,3,'manual'))
    b=evaluate_spokes(s,Point(1,1),Calibration(2,3,'manual'))
    assert a.centroid_physical.center==b.centroid_physical.center
    assert a.centroid_physical.center.x==pytest.approx(4/3)
    assert a.centroid_physical.center.y==pytest.approx(2)
    assert len(a.centroid_pixels.intersections)==3


def test_session_switch_preserves_lines_and_disables_judgment():
    from tests.test_session import ready
    s=ready.__wrapped__(); original=s.spokes
    s.set_center_method('intersection_centroid')
    assert s.spokes==original and not s.can_save and 'spokes' in s.confirmed_steps
    s.confirm_step('result'); record=s.measurement(Limits('px',0,0))
    assert record.judgment.radius==record.judgment.laser_distance=='not_evaluated'
    assert record.result.center_method=='intersection_centroid'


def test_roundtrip_and_centroid_outputs(qapp,tmp_path):
    import csv
    from tests.test_session import ready
    from fistar.storage.repository import connect_database,save_measurement,list_measurements
    from fistar.exporting import export_csv,export_pdf
    s=ready.__wrapped__(); s.set_center_method('intersection_centroid'); s.confirm_step('result')
    r=s.measurement(Limits('px',0,0)); c=connect_database(tmp_path/'db.sqlite')
    save_measurement(c,r); restored=list_measurements(c)[0]
    assert restored.result==r.result and restored.judgment==r.judgment
    assert restored.snapshot['center_method']=='intersection_centroid'
    export_csv((restored,),tmp_path/'summary.csv'); export_pdf(restored,tmp_path/'summary.pdf')
    with (tmp_path/'summary.csv').open() as f: row=next(csv.DictReader(f))
    assert row['中心推定方式']=='交点重心方式'
    assert row['半径']=='' and row['交点までの最大距離']!=''
    assert '偏位評価' not in row
    c.close()


def test_centroid_ui(qapp,tmp_path):
    from tests.test_session import ready
    from fistar.gui.app import MainWindow
    w=MainWindow(database_path=tmp_path/'gui.sqlite'); s=ready.__wrapped__(); w.session=s; w.panel.session=s
    s.set_center_method('minimax');s.confirm_step('result')
    w.refresh();w.panel.center_method.setCurrentIndex(w.panel.center_method.findData('intersection_centroid'))
    assert s.center_method=='intersection_centroid' and not s.can_save
    assert not hasattr(w.panel,'intersection_table')
    w.open_center_detail()
    assert w.detail_window.table.rowCount()==3
    assert '中心偏位' in w.panel.result_label.text()
    s.dirty=False; w.close()


def test_legacy_switch_preserves_saved_minimax(monkeypatch):
    from tests.test_session import ready
    from fistar.core.models import Circle
    from fistar.workflow.session import AnalysisSession
    s=ready.__wrapped__(); r=s.measurement(Limits())
    legacy=replace(r.result,centroid_pixels=None,centroid_physical=None,
        pixels=replace(r.result.pixels,circle=Circle(Point(2.01,2.01),.01)))
    r=replace(r,result=legacy)
    restored=AnalysisSession(); restored.restore(s.image,r)
    assert restored.result==legacy
    def unexpected_recalculation(*args): raise AssertionError('旧記録の最小円を再計算しない')
    monkeypatch.setattr('fistar.core.analysis.minimax_circle',unexpected_recalculation)
    restored.set_center_method('intersection_centroid')
    assert restored.result.pixels==legacy.pixels
    assert restored.result.centroid_pixels is not None


def test_centroid_nonfinite_and_insufficient_directions():
    with pytest.raises(ValueError,match='3本'):
        intersection_centroid(spokes(Line(1,0,1),Line(1,0,2),Line(0,1,0)),Point(0,0),'px')
    with pytest.raises(ValueError,match='非有限'):
        intersection_centroid(spokes(Line(1,0,1e308),Line(1,.001,-1e308),Line(0,1,0)),Point(0,0),'px')


def test_trend_separates_methods(qapp):
    from tests.test_session import ready
    from fistar.gui.records_panel import TrendPlot
    s=ready.__wrapped__(); a=s.measurement(Limits())
    s.set_center_method('intersection_centroid'); s.confirm_step('result'); b=s.measurement(Limits())
    trend=TrendPlot(); trend.records=(a,b); trend.unit='px'
    assert len(trend.points())==1
    trend.center_method='intersection_centroid'
    assert len(trend.points())==1
    trend.close()


def test_unavailable_centroid_cannot_confirm_or_save(qapp,tmp_path,monkeypatch):
    from tests.test_session import ready
    from fistar.gui.app import MainWindow
    s=ready.__wrapped__()
    def fail(*args): raise ValueError('交点が非有限値です')
    monkeypatch.setattr('fistar.core.analysis.intersection_centroid',fail)
    s.set_laser(Point(3,3))
    s.set_detection(s.detection,True)
    for step in s.steps[:5]: s.confirm_step(step)
    w=MainWindow(database_path=tmp_path/'failure.sqlite'); w.session=s; w.panel.session=s
    s.set_center_method('intersection_centroid'); w.refresh()
    assert not s.can_save and '非有限' in w.panel.result_label.text()
    with pytest.raises(ValueError,match='非有限'): s.confirm_step('result')
    s.set_center_method('minimax'); s.confirm_step('result')
    assert s.can_save
    s.dirty=False; w.close()


def test_old_serialized_result_defaults_to_minimax():
    from dataclasses import asdict
    from tests.test_session import ready
    from fistar.storage.repository import measurement_from_dict
    s=ready.__wrapped__(); original=s.measurement(Limits()); data=asdict(original)
    for key in ('centroid_pixels','centroid_physical','centroid_error','center_method'):
        data['result'].pop(key)
    data['snapshot'].pop('center_method')
    restored=measurement_from_dict(data)
    assert restored.result.center_method=='minimax'
    assert restored.result.pixels==original.result.pixels
    assert restored.result.centroid_pixels is None
