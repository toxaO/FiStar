import numpy as np
from pathlib import Path
import pytest
from fistar.core.models import LoadedImage,Point,DetectionSettings
from fistar.workflow.session import AnalysisSession


def test_default_px_and_no_intermediate_confirmation():
    from tests.test_session import ready
    s=ready.__wrapped__()
    s.confirmed_steps.clear()
    assert s.ready_for_review
    s.confirm_step('result')
    assert s.can_save
    s.set_detection_settings(DetectionSettings(.7,.25))
    assert not s.ready_for_review and s.requires_redetection


def test_default_calibration_is_px_and_axis_survives_image_change():
    from fistar.core.models import Calibration
    s=AnalysisSession();s.set_identity('temp','couch')
    s.set_image(LoadedImage(Path('one.tif'),np.zeros((10,10)),'one',Calibration(.1,.2,'TIFF')))
    assert s.calibration is None and s.axis=='couch'


def test_new_ui_and_axis_persistence(qapp,tmp_path):
    from fistar.gui.app import MainWindow
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    assert hasattr(w,'path_edit') and not hasattr(w,'display_low')
    assert not w.panel.confirm_buttons and 'image' not in w.panel.stage_boxes and 'laser' not in w.panel.stage_boxes
    assert not hasattr(w.panel,'polarity')
    w.panel.axis.setCurrentIndex(w.panel.axis.findData('collimator'))
    w.session.dirty=False;w.close()
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    assert w.session.axis=='collimator'
    w.close()


def test_calibration_dropdown_and_live_radius(qapp,tmp_path):
    from fistar.gui.app import MainWindow
    from fistar.core.models import Calibration
    w=MainWindow(database_path=tmp_path/'db.sqlite');s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',Calibration(.1,.2,'TIFF')))
    s.set_laser(Point(50,50));w.refresh()
    assert s.calibration is None
    w.panel.calibration_method.setCurrentIndex(w.panel.calibration_method.findData('tag'))
    assert s.calibration.sx_mm==.1 and s.calibration.sy_mm==.2
    w.panel.calibration_method.setCurrentIndex(w.panel.calibration_method.findData('numeric'))
    w.panel.pixel_length.clear();w.change_calibration('numeric')
    assert s.calibration_error and not s.can_detect
    w.panel.pixel_length.setText('0.1');w.change_calibration('numeric')
    assert s.calibration.sx_mm==pytest.approx(.1) and s.can_detect
    w.panel.calibration_method.setCurrentIndex(w.panel.calibration_method.findData('none'))
    assert s.calibration is None and s.can_detect
    w.overlay_controls.checks['search_circle'].setChecked(False)
    w.panel.radius.setValue(60)
    assert s.detection_settings.radius_ratio==.6 and w.view.visibility['search_circle']
    assert w.panel.radius.toolTip() and w.panel.peak_height.toolTip()
    s.dirty=False;w.close()


def test_path_open_and_single_save_action(qapp,tmp_path):
    import tifffile
    from tests.fixtures.synthetic_starshot import synthetic_starshot
    from fistar.gui.app import MainWindow
    from fistar.core.detection import detect_spokes
    from fistar.storage.repository import list_measurements
    path=tmp_path/'sample.tif';tifffile.imwrite(path,synthetic_starshot((0,25,50,90,120,150)).astype(np.uint16))
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.path_edit.setText(str(path));w.open_button.click()
    s=w.session;assert s.image.path==path and s.calibration is None
    s.set_laser(Point(256,256));s.set_detection(detect_spokes(s.image.raw,s.laser,s.detection_settings));w.refresh()
    assert s.ready_for_review and not s.can_save and w.panel.save_button.isEnabled()
    w.panel.save_button.click()
    assert len(list_measurements(w.connection))==1 and not s.dirty
    w.close()
