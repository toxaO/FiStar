import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from fistar.gui.app import MainWindow
from fistar.core.models import LoadedImage,Point


def test_new_defaults_and_removed_choices(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite')
    w.session.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100,3),np.uint16),'one',None));w.refresh()
    assert w.panel.device.text()=='temp'
    assert w.session.channel=='luminance' and not hasattr(w.panel,'channel')
    assert w.session.center_method=='intersection_centroid'
    assert not hasattr(w,'zoom_tool_button')
    assert w.view.mode=='pan'
    w.session.dirty=False;w.close()


def test_laser_confirmation_switches_to_pan(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'db.sqlite');s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',None))
    for step in s.steps[:3]:s.confirm_step(step)
    s.set_laser(Point(50,50));w.set_mode('laser');w.refresh()
    w.panel.confirm_buttons['laser'].click()
    assert 'laser' in s.confirmed_steps and w.view.mode=='pan'
    s.dirty=False;w.close()


def test_wheel_zoom_uses_display_center_and_preserves_analysis(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();v=w.view;before=v.mapToScene(v.viewport().rect()).boundingRect().center()
    revision=w.session.revision;scale=v.transform().m11()
    event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    v.wheelEvent(event)
    assert v.transform().m11()>scale
    after=v.mapToScene(v.viewport().rect()).boundingRect().center()
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


def test_detail_has_only_pan_and_reset(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/'db.sqlite');w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents();w.open_center_detail();qapp.processEvents();d=w.detail_window
    assert set(d.buttons)=={'pan'}
    assert d.reset_tool_button.icon().isNull()==False
    before=d.view.transform().m11()
    event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
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
    event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    v.wheelEvent(event);zoomed=v.mapToScene(v.viewport().rect()).boundingRect().center()
    assert v.transform().m11()<scale and abs(zoomed.x()-after.x())<.05
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


def test_laser_right_click_and_left_drag_pan(qapp,tmp_path):
    from PySide6.QtTest import QTest
    w=MainWindow(database_path=tmp_path/'db.sqlite');s=w.session
    s.set_image(LoadedImage(tmp_path/'one.tif',np.zeros((100,100),np.uint16),'one',None))
    w.refresh();w.show();qapp.processEvents();w.view.reset_view();w.set_mode('laser');v=w.view
    QTest.mouseClick(v.viewport(),Qt.LeftButton,pos=v.mapFromScene(QPointF(30,40)))
    assert s.laser is None
    QTest.mouseClick(v.viewport(),Qt.RightButton,pos=v.mapFromScene(QPointF(30,40)))
    assert abs(s.laser.x-30)<.2 and abs(s.laser.y-40)<.2
    laser=s.laser;revision=s.revision;before=v.mapToScene(v.viewport().rect()).boundingRect().center()
    QTest.mousePress(v.viewport(),Qt.LeftButton,pos=QPoint(200,200));QTest.mouseMove(v.viewport(),QPoint(250,220));QTest.mouseRelease(v.viewport(),Qt.LeftButton,pos=QPoint(250,220))
    assert v.mapToScene(v.viewport().rect()).boundingRect().center()!=before
    assert s.laser==laser and s.revision==revision
    s.dirty=False;w.close()
