from pathlib import Path
import numpy as np
import pytest
import tifffile
from PySide6.QtCore import Qt,QPoint,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget,QPushButton,QVBoxLayout,QApplication
from fistar.gui.app import MainWindow
from fistar.gui.hover_help import HoverHelp
from fistar.core.models import Point,LoadedImage


def test_resolution_survives_restart_and_reloads_tiff_tags(qapp,tmp_path,monkeypatch):
    first=tmp_path/'first.tif';second=tmp_path/'second.tif'
    tifffile.imwrite(first,np.zeros((30,30),dtype=np.uint16),resolution=(100,200),resolutionunit='INCH')
    tifffile.imwrite(second,np.zeros((30,30),dtype=np.uint16),resolution=(200,400),resolutionunit='INCH')
    db=tmp_path/'test.sqlite';w=MainWindow(database_path=db)
    w.path_edit.setText(str(first));w.load_from_path()
    w.panel.pixel_length.setText('0.123456');w.change_calibration('numeric');w.session.dirty=False;w.close()
    w=MainWindow(database_path=db);w.path_edit.setText(str(second));w.load_from_path()
    assert w.session.calibration_mode=='numeric' and w.session.calibration.sx_mm==pytest.approx(.123456)
    w.change_calibration('tag');assert w.session.calibration.sx_mm==pytest.approx(25.4/200)
    monkeypatch.setattr(w,'allow_discard',lambda:True);w.path_edit.setText(str(first));w.load_from_path()
    assert w.session.calibration.sx_mm==pytest.approx(25.4/100)
    w.session.dirty=False;w.close()


def test_invalid_numeric_does_not_replace_valid_memory(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'test.sqlite')
    w.session.set_image(LoadedImage(Path('dummy.tif'),np.zeros((100,100),dtype=np.uint16),'dummy',None))
    w.panel.pixel_length.setText('.2');w.change_calibration('numeric')
    w.panel.pixel_length.setText('bad');w.change_calibration('numeric')
    assert w.preferences.value('last_pixel_length')=='0.2'
    w.session.dirty=False;w.close()


def test_shift_drag_pans_without_setting_laser(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'test.sqlite');w.backend_state='ready'
    w.session.set_image(LoadedImage(Path('dummy.tif'),np.zeros((100,100),dtype=np.uint16),'dummy',None))
    w.session.set_laser(Point(50,50));w.refresh();w.show();qapp.processEvents();w.set_mode('laser')
    assert w.panel.laser_button.isChecked() and '選択中' in w.panel.laser_button.text()
    viewport=w.view.viewport();start=viewport.rect().center();end=start+QPoint(35,20)
    before=w.view.mapToScene(viewport.rect()).boundingRect().center();revision=w.session.revision
    QTest.mousePress(viewport,Qt.LeftButton,Qt.ShiftModifier,start)
    QTest.mouseMove(viewport,end,20);QTest.mouseRelease(viewport,Qt.LeftButton,Qt.ShiftModifier,end)
    after=w.view.mapToScene(viewport.rect()).boundingRect().center()
    assert before!=after and w.session.laser==Point(50,50) and w.session.revision==revision
    assert w.view.mode=='laser' and w.panel.laser_button.isChecked()
    QTest.mouseClick(viewport,Qt.LeftButton,Qt.NoModifier,start)
    assert w.view.mode=='pan' and not w.panel.laser_button.isChecked()
    assert 'ダブルクリック' in w.operation_help.text()
    w.session.dirty=False;w.close()


def test_hover_help_waits_and_cancels(qapp):
    parent=QWidget();layout=QVBoxLayout(parent);button=QPushButton('help');layout.addWidget(button)
    helper=HoverHelp((button,),'short help',parent,delay_ms=80);parent.show();qapp.processEvents()
    QApplication.sendEvent(button,QEvent(QEvent.Enter))
    assert not helper.popup.isVisible()
    QTest.qWait(110);assert helper.popup.isVisible()
    QApplication.sendEvent(button,QEvent(QEvent.Leave));assert not helper.popup.isVisible()
    QApplication.sendEvent(button,QEvent(QEvent.Enter));QApplication.sendEvent(button,QEvent(QEvent.Leave))
    QTest.qWait(110);assert not helper.popup.isVisible();parent.close()


def test_previous_record_seeds_resolution_preferences(qapp,tmp_path):
    from tests.test_session import ready
    from fistar.core.models import Calibration
    from fistar.storage.repository import connect_database,save_measurement
    s=ready.__wrapped__();s.set_calibration(Calibration(.25,.25,'manual'),'manual');s.confirm_step('result')
    db=tmp_path/'test.sqlite';c=connect_database(db);save_measurement(c,s.measurement());c.close()
    w=MainWindow(database_path=db)
    assert w.preferences.value('last_calibration_method')=='numeric'
    assert float(w.preferences.value('last_pixel_length'))==pytest.approx(.25)
    w.close()
