from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from fistar.gui.app import MainWindow
from fistar.core.models import Point
from fistar.core.imaging import load_tiff
import numpy as np
import tifffile

def test_save_disabled_without_confirmation(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'test.sqlite')
    assert not w.panel.save_button.isEnabled()
    w.close()

def test_pan_does_not_select_laser(qapp,tmp_path):
    p=tmp_path/'image.tif'; tifffile.imwrite(p,np.zeros((100,100),np.uint16))
    w=MainWindow(database_path=tmp_path/'test.sqlite')
    w.session.set_image(load_tiff(p)); w.refresh(); w.show(); qapp.processEvents()
    w.view.set_mode('pan')
    QTest.mouseClick(w.view.viewport(),Qt.LeftButton,pos=QPoint(40,40))
    assert w.session.laser is None
    w.session.dirty=False; w.close()

def test_trend_can_render_in_records(qapp,tmp_path):
    import subprocess,sys,os
    code='from PySide6.QtWidgets import QApplication; from fistar.gui.records_panel import TrendPlot; a=QApplication([]); p=TrendPlot(); p.show(); a.processEvents(); p.grab(); p.close()'
    result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True)
    assert result.returncode==0,result.stderr.decode()

def test_detection_fields_restore_and_reset(qapp,tmp_path):
    from fistar.core.models import LoadedImage,DetectionSettings
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    w.session.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',None))
    w.session.set_detection_settings(DetectionSettings(.65,.4,'bright')); w.refresh()
    assert w.panel.radius.value()==65 and w.panel.peak_height.value()==40
    assert w.panel.polarity.currentData()=='bright'
    w.session.set_image(LoadedImage(tmp_path/'two.tif',np.zeros((100,100),np.uint16),'two',None)); w.refresh()
    assert w.panel.radius.value()==85 and w.panel.peak_height.value()==25 and w.panel.polarity.currentData()=='dark'
    w.session.dirty=False; w.close()

def test_display_adjustment_preserves_raw_and_state(qapp,tmp_path):
    from fistar.core.models import LoadedImage
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    raw=np.arange(10000,dtype=np.uint16).reshape(100,100)
    w.session.set_image(LoadedImage(tmp_path/'one.tif',raw,'hash',None)); w.refresh()
    revision=w.session.revision
    w.view.set_display_range(2000,4000)
    assert w.session.revision==revision
    np.testing.assert_array_equal(w.session.image.raw,raw)
    assert '100' in w.panel.image_label.text() and '16' in w.panel.image_label.text()
    w.session.dirty=False; w.close()

def test_no_profile_widget(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    assert not hasattr(w.panel,'profile')
    w.close()

def test_stage_controls_require_predecessors(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    assert not w.panel.device.isEnabled()
    w.session.set_image(__import__('fistar.core.models',fromlist=['LoadedImage']).LoadedImage(tmp_path/'one.tif',np.zeros((10,10),np.uint16),'hash',None)); w.refresh()
    assert not w.panel.device.isEnabled()
    w.session.confirm_step('image'); w.refresh()
    assert w.panel.device.isEnabled()
    assert not w.panel.known_length.isEnabled()
    w.session.dirty=False; w.close()

def test_save_failure_keeps_confirmed_work(qapp,tmp_path):
    from tests.test_session import ready
    # Use the real session setup through its underlying fixture function.
    session=ready.__wrapped__()
    w=MainWindow(database_path=tmp_path/'db.sqlite'); w.session=session; w.panel.session=session
    w.connection.close(); errors=[]; w.show_error=errors.append
    assert not w.save()
    assert w.session.dirty and w.session.can_save and errors
    w.session.dirty=False; w.close()

def test_removed_edit_modes_and_manual_calibration(qapp,tmp_path):
    from tests.test_session import ready
    from PySide6.QtCore import QPointF
    s=ready.__wrapped__()
    w=MainWindow(database_path=tmp_path/'db.sqlite'); w.session=s; w.panel.session=s
    w.refresh(); w.show(); qapp.processEvents(); w.view.reset_view()
    import pytest
    for mode in ('spoke','add','zoom'):
        with pytest.raises(ValueError): w.view.set_mode(mode)
    w.view.set_mode('calibration'); w.panel.known_length.setValue(10)
    QTest.mouseClick(w.view.viewport(),Qt.LeftButton,pos=w.view.mapFromScene(QPointF(1,1)))
    QTest.mouseClick(w.view.viewport(),Qt.LeftButton,pos=w.view.mapFromScene(QPointF(5,1)))
    assert s.calibration.source=='manual'
    assert abs(s.calibration.sx_mm-2.5)<.03
    s.dirty=False; w.close()

def test_async_detection_finishes_in_current_session(qapp,tmp_path):
    import time
    from fistar.core.models import LoadedImage,DetectionSettings
    from tests.fixtures.synthetic_starshot import synthetic_starshot
    w=MainWindow(database_path=tmp_path/'db.sqlite'); s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',synthetic_starshot((0,25,50,90,120,150)),'hash',None))
    s.set_identity('装置','gantry'); s.set_laser(Point(256,256))
    for step in s.steps[:4]: s.confirm_step(step)
    w.refresh(); w.detect(DetectionSettings(.8,.25))
    end=time.monotonic()+5
    while w._workers and time.monotonic()<end:
        qapp.processEvents(); QTest.qWait(10)
    assert not w._workers and len(s.spokes)==6 and not s.can_save
    s.dirty=False; w.close()

def test_failed_detection_preserves_manual_lines(qapp,tmp_path):
    from tests.test_session import ready
    s=ready.__wrapped__()
    w=MainWindow(database_path=tmp_path/'failure.sqlite'); w.session=s; w.panel.session=s
    before=tuple(s.spokes); detection=s.detection; errors=[]; w.show_error=errors.append
    w.detection_finished(s.revision,s.image.sha256,None,'検出点が奇数です')
    assert tuple(s.spokes)==before and s.detection==detection
    assert errors==['検出点が奇数です']
    assert '検出できません' in w.statusBar().currentMessage()
    s.dirty=False; w.close()
