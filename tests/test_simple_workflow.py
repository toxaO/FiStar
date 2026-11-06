import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from fistar.gui.app import MainWindow
from fistar.core.models import LoadedImage,Point


def test_new_defaults_and_removed_choices(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    w.session.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100,3),np.uint16),'one',None));w.refresh()
    assert w.panel.device.isEditable() and w.panel.device.currentText()==''
    w.panel.device.setEditText('装置A')
    assert w.session.device=='装置A'
    assert w.session.channel=='luminance' and not hasattr(w.panel,'channel')
    assert w.session.center_method=='intersection_centroid'
    assert not w.zoom_tool_button.icon().isNull()
    assert w.view.mode=='pan'
    w.session.dirty=False;w.close()


def test_laser_selection_does_not_need_intermediate_confirmation(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite');s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',None))
    s.set_laser(Point(50,50));w.refresh()
    assert 'laser' in w.panel.stage_boxes and not w.panel.confirm_buttons
    assert not s.confirmed_steps and w.panel.detect_button.isEnabled()
    assert w.view.mode=='pan'
    s.dirty=False;w.close()

def test_wheel_zoom_uses_cursor_and_preserves_analysis(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();v=w.view;anchor=v.mapFromScene(v._image_item.boundingRect().center())+QPoint(20,0);before=v.mapToScene(anchor)
    revision=w.session.revision;scale=v.transform().m11()
    event=QWheelEvent(QPointF(anchor),QPointF(anchor),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    v.wheelEvent(event)
    assert v.transform().m11()>scale
    after=v.mapToScene(anchor)
    assert abs(before.x()-after.x())<.1 and abs(before.y()-after.y())<.1
    assert w.session.revision==revision
    w.session.dirty=False;w.close()


def test_luminance_display_and_legacy_channel_protection(qapp,tmp_path):
    from dataclasses import replace
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    raw=np.zeros((100,100,3),np.uint16);raw[:,:,0]=11;raw[:,:,1]=22;raw[:,:,2]=33
    w.session.set_image(LoadedImage(tmp_path/'rgb.tif',raw,'rgb',None));w.refresh()
    assert np.allclose(w.view._values,.299*11+.587*22+.114*33)
    s=ready.__wrapped__();s.channel='R';s.confirmed_steps.discard('result')
    import pytest
    with pytest.raises(ValueError,match='輝度で再検出'):s.confirm_step('result')
    assert not s.can_save
    s.set_detection(s.detection,True)
    assert s.channel=='luminance'
    w.session.dirty=False;w.close()


def test_detail_has_navigation_tools(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();w.open_center_detail();qapp.processEvents();d=w.detail_window
    assert set(d.buttons)=={'pan','zoom'}
    assert d.reset_tool_button.icon().isNull()==False
    before=d.view.transform().m11()
    anchor=QPointF(d.view.viewport().rect().center())
    event=QWheelEvent(anchor,anchor,QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    d.view.wheelEvent(event)
    assert d.view.transform().m11()>before and not d._auto_fit_active
    w.session.dirty=False;w.close()


def test_pan_works_at_full_image_scale(qapp,tmp_path):
    from PySide6.QtTest import QTest
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();v=w.view;v.reset_view()
    before=v.mapToScene(v.viewport().rect()).boundingRect().center();scale=v.transform().m11()
    QTest.mousePress(v.viewport(),Qt.LeftButton,pos=QPoint(200,200));QTest.mouseMove(v.viewport(),QPoint(250,220));QTest.mouseRelease(v.viewport(),Qt.LeftButton,pos=QPoint(250,220))
    after=v.mapToScene(v.viewport().rect()).boundingRect().center()
    assert abs(after.x()-(before.x()-50/scale))<.05
    anchor=v.mapFromScene(v._image_item.boundingRect().center())
    anchored=v.mapToScene(anchor)
    event=QWheelEvent(QPointF(anchor),QPointF(anchor),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    v.wheelEvent(event);zoomed=v.mapToScene(anchor)
    assert v.transform().m11()<scale and abs(zoomed.x()-anchored.x())<.05
    w.session.dirty=False;w.close()


def test_detail_double_click_resets_to_all_points(qapp,tmp_path):
    from PySide6.QtTest import QTest
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();w.open_center_detail();qapp.processEvents();d=w.detail_window
    d.manual_navigation();d.view.zoom_in()
    QTest.mouseDClick(d.view.viewport(),Qt.LeftButton,pos=QPoint(200,200));qapp.processEvents()
    assert d._auto_fit_active
    w.session.dirty=False;w.close()


def test_laser_left_click_and_shift_drag_pan(qapp,tmp_path):
    from PySide6.QtTest import QTest
    w=MainWindow(database_path=tmp_path/'db.sqlite');s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',None))
    w.refresh();w.show();qapp.processEvents();w.view.reset_view();w.set_mode('laser');v=w.view
    QTest.mouseClick(v.viewport(),Qt.RightButton,pos=v.mapFromScene(QPointF(30,40)))
    assert s.laser is None and v.mode=='laser'
    before=v.mapToScene(v.viewport().rect()).boundingRect().center();revision=s.revision
    QTest.mousePress(v.viewport(),Qt.LeftButton,Qt.ShiftModifier,QPoint(200,200));QTest.mouseMove(v.viewport(),QPoint(250,220));QTest.mouseRelease(v.viewport(),Qt.LeftButton,Qt.ShiftModifier,QPoint(250,220))
    assert v.mapToScene(v.viewport().rect()).boundingRect().center()!=before
    assert s.laser is None and s.revision==revision and v.mode=='laser'
    QTest.mouseClick(v.viewport(),Qt.LeftButton,pos=v.mapFromScene(QPointF(30,40)))
    assert abs(s.laser.x-30)<.2 and abs(s.laser.y-40)<.2 and v.mode=='pan'
    laser=s.laser;revision=s.revision
    before=v.mapToScene(v.viewport().rect()).boundingRect().center()
    QTest.mousePress(v.viewport(),Qt.LeftButton,pos=QPoint(200,200));QTest.mouseMove(v.viewport(),QPoint(250,220));QTest.mouseRelease(v.viewport(),Qt.LeftButton,pos=QPoint(250,220))
    assert v.mapToScene(v.viewport().rect()).boundingRect().center()!=before
    assert s.laser==laser and s.revision==revision
    s.dirty=False;w.close()

def test_navigation_preserves_ruler_point_and_circle_uses_analysis_values(qapp,tmp_path):
    from PySide6.QtTest import QTest
    from fistar.gui.image_view import NAVIGATION_CONTROL_MODIFIER

    w=MainWindow(database_path=tmp_path/'db.sqlite')
    pixels=np.zeros((100,100),np.uint16)
    pixels[30:61,30:61]=1234
    w.session.set_image(LoadedImage(tmp_path/'one.tif',pixels,'one',None))
    w.refresh();w.show();qapp.processEvents()
    view=w.view
    viewport=view.viewport()
    w.set_mode('ruler')
    start=view.mapFromScene(QPointF(40,40))
    QTest.mouseClick(viewport,Qt.LeftButton,pos=start)
    first=view.ruler_points[0]
    QTest.keyPress(view,Qt.Key_Shift)
    assert w.pan_tool_button.isChecked() and not w.ruler_tool_button.isChecked()
    QTest.keyRelease(view,Qt.Key_Shift)
    assert w.ruler_tool_button.isChecked() and view.ruler_points==(first,)
    scale=view.transform().m11()
    QTest.mousePress(viewport,Qt.LeftButton,NAVIGATION_CONTROL_MODIFIER,start)
    QTest.mouseMove(viewport,start+QPoint(0,-60))
    QTest.mouseRelease(viewport,Qt.LeftButton,NAVIGATION_CONTROL_MODIFIER,start+QPoint(0,-60))
    assert view.transform().m11()>scale
    assert view.mode=='ruler' and view.ruler_points==(first,)
    QTest.mouseClick(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(55,55)))
    assert len(view.ruler_points)==2
    before=view.ruler_points
    QTest.mouseClick(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(55,55))+QPoint(3,0))
    assert view.ruler_points==before
    QTest.mousePress(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(55,55)))
    QTest.mouseMove(viewport,view.mapFromScene(QPointF(60,55)))
    QTest.mouseRelease(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(60,55)))
    assert view.ruler_points[1].x>59

    w.begin_ruler_calibration()
    w.ruler_known.setText('10')
    start=view.mapFromScene(QPointF(40,40))
    QTest.mouseClick(viewport,Qt.LeftButton,pos=start)
    QTest.mousePress(viewport,Qt.LeftButton,Qt.ShiftModifier,start)
    QTest.mouseMove(viewport,start+QPoint(20,10))
    QTest.mouseRelease(viewport,Qt.LeftButton,Qt.ShiftModifier,start+QPoint(20,10))
    assert w._ruler_calibrating and len(view.ruler_points)==1
    QTest.mouseClick(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(60,40)))
    assert not w._ruler_calibrating
    assert abs(w.session.calibration.sx_mm-.5)<.01

    revision=w.session.revision
    w.circle_tool_button.click()
    QTest.mousePress(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(45,45)))
    QTest.mouseMove(viewport,view.mapFromScene(QPointF(55,45)))
    QTest.mouseRelease(viewport,Qt.LeftButton,pos=view.mapFromScene(QPointF(55,45)))
    assert '1234' in w.operation_help.text()
    assert w.session.revision==revision
    w.session.dirty=False;w.close()
