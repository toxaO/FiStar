from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from fistar.core.models import *
from fistar.workflow.session import AnalysisSession

@pytest.fixture
def ready():
    s=AnalysisSession()
    s.set_image(LoadedImage(Path('test.tif'),np.zeros((10,10)),'hash',None))
    s.set_center_method('minimax')
    s.set_identity('装置','gantry')
    s.set_calibration(None)
    s.set_laser(Point(2,2))
    s.set_detection(DetectionResult(tuple(Spoke(str(i),l) for i,l in enumerate((Line(1,0,2),Line(0,1,2),Line(1,1,4)))),DetectionSettings()))
    for step in s.steps: s.confirm_step(step)
    return s

def test_save_gated_and_snapshot(ready):
    assert ready.can_save
    assert ready.snapshot()['schema_version']==4
    ready.set_laser(Point(3,3))
    assert not ready.can_save
    assert len(ready.spokes)==3
    assert ready.result.pixels.laser_distance == pytest.approx(2**.5)
    assert 'spokes' not in ready.confirmed_steps

def test_edit_invalidates_and_keeps_original(ready):
    old=ready.spokes[0]
    ready.replace_spoke(replace(old,line=Line(1,0,3),origin='manual'))
    assert not ready.can_save
    assert ready.snapshot()['detected_spokes'][0]['line']['offset']==2
    assert ready.snapshot()['spokes'][0]['line']['offset']==3
    with pytest.raises(ValueError): ready.set_channel('R')

def test_order_and_stale(ready):
    s=AnalysisSession()
    with pytest.raises(ValueError): s.confirm_step('result')
    revision=ready.revision
    ready.set_laser(Point(5,5))
    assert not ready.apply_detection(revision,'hash',ready.detection)

def test_unchanged_identity_preserves_confirmation(ready):
    revision=ready.revision
    ready.set_identity('装置','gantry')
    assert ready.revision==revision and ready.can_save

def test_restore_legacy_keeps_settings_lines_and_result():
    from copy import deepcopy
    from dataclasses import asdict
    image=LoadedImage(Path('legacy.tif'),np.zeros((10,10)),'legacy-hash',None)
    spokes=tuple(Spoke(str(i),l) for i,l in enumerate((Line(1,0,2),Line(0,1,2),Line(1,1,4))))
    legacy_settings={'inner_radius_px':1,'outer_radius_px':4,'threshold':123,'polarity':'bright'}
    snapshot={'schema_version':1,'image_path':'legacy.tif','image_sha256':'legacy-hash','channel':'luminance','calibration':None,'laser':{'x':2,'y':2},'detection_settings':legacy_settings,'detected_spokes':[asdict(s) for s in spokes],'spokes':[asdict(s) for s in spokes]}
    original=deepcopy(snapshot)
    metric=MetricResult('px',Circle(Point(2,2),0),Point(0,0),0)
    record=Measurement('old','2026-10-01T12:00:00+09:00','旧装置','gantry','legacy.tif',AnalysisResult(metric,None,('0','1','2')),Limits(),Judgment('unset','unset'),snapshot)
    session=AnalysisSession(); session.restore(image,record)
    assert session.result==record.result and session.spokes==spokes
    assert session.detection_settings==DetectionSettings()
    assert session.detection.settings==legacy_settings
    assert session.detection.method=='legacy-threshold-tls'
    assert record.snapshot==original
    # Saving after a manual edit must not relabel the original detector as Pylinac.
    session.replace_spoke(replace(spokes[0],origin='manual',line=Line(1,0,3)))
    for step in ('spokes','result'): session.confirm_step(step)
    saved=session.measurement(Limits())
    assert saved.snapshot['detection_metadata']['settings']==legacy_settings
    assert saved.snapshot['detection_metadata']['method']=='legacy-threshold-tls'

def test_snapshot_pylinac_metadata_roundtrip():
    from fistar.core.detection import detect_spokes
    from tests.fixtures.synthetic_starshot import synthetic_starshot
    image=LoadedImage(Path('new.tif'),synthetic_starshot((0,25,50,90,120,150)),'new-hash',None)
    session=AnalysisSession(); session.set_image(image); session.set_identity('装置','gantry'); session.set_laser(Point(256,256))
    detection=detect_spokes(image.raw,session.laser,DetectionSettings())
    session.set_detection(detection)
    for step in session.steps: session.confirm_step(step)
    record=session.measurement(Limits())
    assert record.snapshot['detection_metadata']['pylinac_version']=='3.48.0'
    restored=AnalysisSession(); restored.restore(image,record)
    assert restored.detection==detection
    assert restored.result==record.result and not restored.can_save
