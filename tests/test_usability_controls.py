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


def test_stage_titles_and_help_icons_match_firec(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'stage-help.sqlite')
    w.show();qapp.processEvents()
    before=w.session.snapshot();stage=w.panel.current_stage
    positions={key:box.geometry() for key,box in w.panel.stage_boxes.items()}
    for key in w.panel.stage_order:
        box=w.panel.stage_boxes[key]
        assert box.title()==w.panel.stage_titles[key]
        assert box.font().pixelSize()==15
        button=w.panel.stage_help_buttons[key];helper=w.panel.stage_help[key]
        assert button.isEnabled() and not button.icon().pixmap(24,24).isNull()
        assert helper.timer.interval()==1000
        QApplication.sendEvent(button,QEvent(QEvent.Enter))
        QTest.qWait(20)
        assert not helper.popup.isVisible()
        QApplication.sendEvent(button,QEvent(QEvent.Leave))
        assert not helper.timer.isActive()
        button.click();qapp.processEvents()
        assert helper.popup.isVisible()
        assert w.panel.current_stage==stage and w.session.snapshot()==before
        assert {key:box.geometry() for key,box in w.panel.stage_boxes.items()}==positions
        helper.popup.hide()
    w.close()


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


def test_step_frames_preserve_analysis_and_only_select_edit_target(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/"navigation.sqlite")
    w.session=ready.__wrapped__();w.panel.session=w.session
    w.refresh();w.show();qapp.processEvents()
    w.set_mode("ruler")
    before=w.session.snapshot();revision=w.session.revision;dirty=w.session.dirty
    result=w.session.result
    scroll=w.analysis_scroll.verticalScrollBar().value()
    positions={stage:w.panel.stage_boxes[stage].geometry() for stage in w.panel.stage_order}
    for stage in ("identity","laser","calibration","spokes","result","laser"):
        QTest.mouseClick(w.panel.stage_boxes[stage],Qt.LeftButton,Qt.NoModifier,QPoint(2,2))
        assert w.panel.current_stage==stage
        assert w.panel.stage_boxes[stage].property("currentStage")
        assert w.session.snapshot()==before and w.session.revision==revision
        assert w.session.dirty==dirty and w.session.result is result
        assert w.view.mode=="ruler" and not w.panel.laser_button.isChecked()
    QTest.mouseClick(w.panel.stage_headers["identity"],Qt.LeftButton,pos=QPoint(2,2))
    assert w.panel.current_stage=="identity"
    w.select_stage("laser")
    QTest.mouseClick(w.panel.radius,Qt.LeftButton,Qt.NoModifier,QPoint(8,8))
    assert w.panel.current_stage=="laser"
    qapp.processEvents()
    assert w.analysis_scroll.verticalScrollBar().value()==scroll
    assert positions=={stage:w.panel.stage_boxes[stage].geometry() for stage in w.panel.stage_order}
    QTest.keyClick(w.panel.stage_headers["laser"],Qt.Key_PageDown,Qt.ControlModifier)
    assert w.panel.current_stage=="calibration"
    QTest.keyClick(w.panel.stage_headers["calibration"],Qt.Key_PageUp,Qt.ControlModifier)
    assert w.panel.current_stage=="laser"
    assert w.session.snapshot()==before and w.view.mode=="ruler"
    w.tabs.setCurrentIndex(1);w.move_stage(1)
    assert w.panel.current_stage=="laser"
    w.tabs.setCurrentIndex(0)
    w.session.set_laser(Point(3,3));w.refresh()
    assert w.panel.stage_boxes["spokes"].property("stepState")=="stale"
    assert w.panel.stage_boxes["result"].property("stepState")=="stale"
    assert w.panel.stage_boxes["laser"].property("stepState")=="complete"
    w.session.dirty=False;w.close()


def test_step_frames_remain_available_before_loading_image(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/"empty-navigation.sqlite")
    w.show();qapp.processEvents()
    assert not w.panel.radius.isEnabled()
    assert w.panel.stage_boxes["spokes"].property("stepState")=="incomplete"
    for stage in w.panel.stage_order:
        assert w.panel.stage_headers[stage].isEnabled()
        assert w.panel.stage_boxes[stage].isVisible()
        QTest.mouseClick(w.panel.stage_boxes[stage],Qt.LeftButton,Qt.NoModifier,QPoint(2,2))
        assert w.panel.current_stage==stage
    QTest.keyClick(w.panel.stage_help_buttons["result"],Qt.Key_Tab)
    assert w.panel.current_stage=="result"
    assert w.view.mode=="pan" and w.session.image is None
    w.close()


def test_incomplete_result_blocks_save_without_confirmation_button(qapp,tmp_path,monkeypatch):
    w=MainWindow(database_path=tmp_path/"incomplete.sqlite")
    errors=[];monkeypatch.setattr(w,"show_error",errors.append)
    assert not hasattr(w.panel,"review_button") and not hasattr(w,"review_result")
    assert not w.panel.save_button.isEnabled() and not w.save()
    assert errors and "画像" in errors[-1]
    assert not w.session.can_save
    assert w.connection.execute("SELECT COUNT(*) FROM measurements_v1").fetchone()[0]==0
    w.close()


def test_result_completes_automatically_and_invalid_changes_block_save(qapp,tmp_path,monkeypatch):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/"auto-result.sqlite")
    w.session=ready.__wrapped__();w.panel.session=w.session
    w.session.confirmed_steps.clear();w.refresh();w.show();qapp.processEvents()
    errors=[];monkeypatch.setattr(w,"show_error",errors.append)
    current=w.panel.current_stage;scroll=w.analysis_scroll.verticalScrollBar().value()
    assert w.session.can_save and w.panel.save_button.isEnabled()
    assert w.panel.stage_boxes["result"].property("stepState")=="complete"
    assert w.connection.execute("SELECT COUNT(*) FROM measurements_v1").fetchone()[0]==0
    w.session.set_laser(Point(3,3));w.refresh()
    assert w.panel.stage_boxes["result"].property("stepState")=="stale"
    assert not w.session.can_save and not w.panel.save_button.isEnabled() and not w.save()
    assert "再検出" in errors[-1]
    w.session.set_detection(w.session.detection);w.refresh()
    assert w.session.can_save and w.panel.stage_boxes["result"].property("stepState")=="complete"
    w.panel.dpi_input.setText("0");w.change_calibration("dpi")
    assert w.session.calibration_error and not w.session.can_save and not w.panel.save_button.isEnabled()
    assert w.panel.stage_boxes["result"].property("stepState")=="incomplete"
    w.panel.dpi_input.setText("254");w.change_calibration("dpi")
    assert w.session.can_save and w.panel.save_button.isEnabled()
    assert w.panel.current_stage==current and w.analysis_scroll.verticalScrollBar().value()==scroll
    w.session.dirty=False;w.close()


def test_save_action_stays_inside_result_card(qapp,tmp_path):
    from tests.test_session import ready
    w=MainWindow(database_path=tmp_path/"result-layout.sqlite")
    w.session=ready.__wrapped__();w.panel.session=w.session;w.refresh()
    w.show();qapp.processEvents()
    box=w.panel.stage_boxes["result"]
    assert not hasattr(w.panel,"review_button")
    assert w.panel.save_button.parentWidget() is box
    assert w.panel.center_method.y()<w.panel.result_label.y()<w.panel.save_button.y()
    assert w.panel.save_button.text()=="保存"
    assert w.panel.save_button.property("primary") and 72<=w.panel.save_button.width()<=120
    w.session.dirty=False;w.close()


def test_dpi_default_conversion_tag_display_and_restart(qapp,tmp_path,monkeypatch):
    image=tmp_path/"dpi.tif"
    tifffile.imwrite(image,np.zeros((30,30),dtype=np.uint16),resolution=(100,200),resolutionunit="INCH")
    db=tmp_path/"dpi.sqlite";w=MainWindow(database_path=db)
    assert w.panel.calibration_method.currentData()=="dpi"
    w.path_edit.setText(str(image));w.load_from_path()
    assert w.session.calibration_mode=="dpi"
    assert w.session.calibration.sx_mm==pytest.approx(25.4/100)
    w.panel.dpi_input.setText("254");w.change_calibration("dpi")
    assert w.session.calibration.sx_mm==pytest.approx(.1)
    assert "254" in w.image_info.text() and "DPI" in w.panel.summary.text()
    w.session.dirty=False;w.close()
    w=MainWindow(database_path=db);w.path_edit.setText(str(image));w.load_from_path()
    assert w.session.calibration_mode=="dpi" and w.session.calibration.sx_mm==pytest.approx(.1)
    w.change_calibration("tag")
    assert w.session.calibration.sx_mm==pytest.approx(25.4/100)
    assert w.session.calibration.sy_mm==pytest.approx(25.4/200)
    assert "X 100" in w.image_info.text() and "Y 200" in w.image_info.text() and "DPI" in w.image_info.text()
    assert "X 100" in w.panel.calibration_label.text() and "Y 200" in w.panel.summary.text()
    assert "X 100" in w.panel.tag_dpi_label.text() and "Y 200" in w.panel.tag_dpi_label.text()
    w.change_calibration("dpi")
    assert w.session.calibration.sx_mm==pytest.approx(.1)
    w.session.dirty=False;w.close()


@pytest.mark.parametrize("value",["0","-1","nan","inf","bad"])
def test_invalid_dpi_preserves_valid_preference(qapp,tmp_path,value):
    w=MainWindow(database_path=tmp_path/"invalid-dpi.sqlite")
    w.session.set_image(LoadedImage(Path("dummy.tif"),np.zeros((30,30)),"dummy",None))
    w.panel.dpi_input.setText("127");w.change_calibration("dpi")
    w.panel.dpi_input.setText(value);w.change_calibration("dpi")
    assert w.session.calibration_error and not w.session.can_detect
    assert float(w.preferences.value("last_dpi"))==pytest.approx(127)
    assert "DPI" in w.session.calibration_error
    w.session.dirty=False;w.close()


def test_image_information_stays_at_bottom_with_compact_height(qapp,tmp_path):
    from PySide6.QtWidgets import QStatusBar
    w=MainWindow(database_path=tmp_path/"footer.sqlite")
    w.session.set_image(LoadedImage(Path("sample.tif"),np.zeros((30,30),dtype=np.uint16),"sample",None));w.refresh()
    w.show();qapp.processEvents()
    assert isinstance(w.image_info.parentWidget(),QStatusBar)
    assert w.image_info.height()<=w.image_info.fontMetrics().lineSpacing()+8
    w.statusBar().showMessage("検出しています");qapp.processEvents()
    assert w.image_info.isVisible() and "sample.tif" in w.image_info.text()
    w.session.dirty=False;w.close()


def test_main_image_resizes_square_with_margins_and_full_width_file_row(qapp,tmp_path):
    from tests.test_session import ready
    from PySide6.QtWidgets import QSplitter
    w=MainWindow(database_path=tmp_path/"square-resize.sqlite")
    w.session=ready.__wrapped__();w.panel.session=w.session;w.refresh();w.show();qapp.processEvents()
    w.view.zoom_in();w.set_mode("ruler")
    snapshot=w.session.snapshot();revision=w.session.revision;scale=w.view.transform().m11()
    splitter=w.square_image.parentWidget().parentWidget()
    assert isinstance(splitter,QSplitter)
    previous_side=None
    for size,pane_sizes in (((1400,650),(950,400)),((760,1050),(400,330)),((1150,850),(650,450))):
        w.resize(*size);splitter.setSizes(pane_sizes);qapp.processEvents();qapp.processEvents()
        area=w.square_image;geometry=w.view.geometry()
        assert geometry.width()==geometry.height()
        assert geometry.left()>=8 and geometry.top()>=8
        assert area.width()-geometry.right()-1>=8 and area.height()-geometry.bottom()-1>=8
        assert abs(geometry.center().x()-area.rect().center().x())<=1
        assert abs(geometry.center().y()-area.rect().center().y())<=1
        assert area.rect().contains(geometry)
        assert w.session.snapshot()==snapshot and w.session.revision==revision
        assert w.view.mode=="ruler" and w.view.transform().m11()==pytest.approx(scale)
        row=w.path_edit.parentWidget()
        assert row.width()-w.open_button.geometry().right()-1<=8
        if size[0]==1400:assert w.path_edit.width()>340
        if previous_side is not None:assert previous_side!=geometry.width()
        previous_side=geometry.width()
    w.session.dirty=False;w.close()
