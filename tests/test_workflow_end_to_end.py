from pathlib import Path
from dataclasses import replace
import numpy as np
import pytest
import tifffile
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from fistar.gui.app import MainWindow
from fistar.core.models import *
from fistar.core.imaging import load_tiff,analysis_channel,manual_calibration
from fistar.core.detection import detect_spokes
from fistar.storage.repository import list_measurements
from fistar.exporting import export_csv,export_pdf
from tests.fixtures.synthetic_starshot import synthetic_starshot

@pytest.fixture
def completed_workflow(qapp,tmp_path):
    p=tmp_path/'synthetic.tif'
    tifffile.imwrite(p,synthetic_starshot((0,25,50,90,120,150)).astype(np.uint16),resolution=(100,200),resolutionunit='INCH')
    w=MainWindow(database_path=tmp_path/'test.sqlite')
    s=w.session; s.set_image(load_tiff(p)); s.set_identity('合成装置','gantry'); s.set_calibration(manual_calibration(Point(0,0),Point(100,0),10)); s.set_laser(Point(256,256))
    for step in s.steps[:4]: s.confirm_step(step)
    d=detect_spokes(analysis_channel(s.image),s.laser,s.detection_settings); s.set_detection(d)
    old=s.spokes[0]; s.replace_spoke(replace(old,line=Line(old.line.nx,old.line.ny,old.line.offset+1),origin='manual'))
    for step in s.steps[4:]: s.confirm_step(step)
    w.refresh(); assert w.panel.save_button.isEnabled()
    QTest.mouseClick(w.panel.save_button,Qt.LeftButton)
    restored=list_measurements(w.connection); assert len(restored)==1
    record=restored[0]; csv_path=tmp_path/'summary.csv'; pdf_path=tmp_path/'summary.pdf'
    export_csv(restored,csv_path); export_pdf(record,pdf_path)
    w.session.dirty=False; w.close()
    return record,restored,csv_path,pdf_path,p

def test_saved_workflow(completed_workflow):
    record,restored,csv_path,pdf_path,p=completed_workflow
    assert restored[0].result==record.result
    assert record.snapshot['spokes'][0]['origin']=='manual'
    assert record.snapshot['calibration']['reference'][2]==10
    assert csv_path.is_file() and pdf_path.is_file()

def test_restore_and_stale_worker(qapp,tmp_path,completed_workflow):
    record,_,_,_,p=completed_workflow
    w=MainWindow(database_path=tmp_path/'other.sqlite')
    w.reopen_record(record)
    assert w.session.result==record.result
    assert not w.session.can_save
    revision=w.session.revision
    w.session.set_image(load_tiff(p)); new_revision=w.session.revision
    w.detection_finished(revision,record.snapshot['image_sha256'],DetectionResult((),DetectionSettings()),'')
    assert w.session.revision==new_revision and not w.session.spokes
    w.session.dirty=False; w.close()

@pytest.mark.parametrize('name',['starshot-12.tif','starshot-18.tif'])
@pytest.mark.parametrize('method',['minimax','intersection_centroid'])
def test_sample_load_edit_save_export(qapp,tmp_path,name,method):
    p=Path(__file__).parents[1]/'sample/images'/name
    w=MainWindow(database_path=tmp_path/'sample.sqlite'); s=w.session
    s.set_image(load_tiff(p)); s.set_identity('サンプル検証','collimator')
    h,width=s.image.raw.shape[:2]; s.set_laser(Point(width/2,h/2))
    for step in s.steps[:4]: s.confirm_step(step)
    d=detect_spokes(analysis_channel(s.image),s.laser,DetectionSettings()); s.set_detection(d)
    assert len(s.spokes)>=3  # Software operation only: no independent count/precision reference exists.
    old=s.spokes[0]; s.replace_spoke(replace(old,line=Line(old.line.nx,old.line.ny,old.line.offset+.2),origin='manual'))
    s.set_center_method(method)
    for step in s.steps[4:]: s.confirm_step(step)
    w.refresh(); assert w.save()
    record=list_measurements(w.connection)[0]; export_csv((record,),tmp_path/'sample.csv'); export_pdf(record,tmp_path/'sample.pdf')
    w.reopen_record(record)
    s=w.session
    assert s.result==record.result
    assert s.detection.points==d.points and s.detection.pylinac_version=='3.48.0'
    assert s.spokes[0].origin=='manual'
    assert s.center_method==method
    if method=='intersection_centroid':
        assert s.result.selected.intersections==record.result.selected.intersections
        assert record.judgment.radius==record.judgment.laser_distance=='not_evaluated'
    w.grab().save(str(tmp_path/'sample-window.png'))
    w.close()

def test_sample_minimax_stable_for_adjusted_circle():
    from fistar.core.analysis import evaluate_spokes
    image=load_tiff(Path(__file__).parents[1]/'sample/images/starshot-18.tif')
    h,w=image.raw.shape[:2]; laser=Point(w/2,h/2)
    detection=detect_spokes(analysis_channel(image),laser,DetectionSettings(.6,.25))
    result=evaluate_spokes(detection.spokes,laser,image.tagged_calibration)
    assert np.isfinite(result.primary.circle.radius)
