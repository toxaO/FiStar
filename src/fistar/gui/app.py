import sys
import math
from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QStandardPaths,QSize,QSettings,QTimer
from PySide6.QtWidgets import (QApplication,QToolButton,QGroupBox,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QScrollArea,QTabWidget,QPushButton,QLabel,QFileDialog,QMessageBox,QDialog,QFormLayout,QComboBox,QLineEdit,QDialogButtonBox,QDoubleSpinBox,QFrame,QSizePolicy)
from PySide6.QtGui import QIcon
from fistar.core.imaging import load_tiff,analysis_channel,manual_calibration
from fistar.workflow.session import AnalysisSession
from fistar.core.detection import detect_spokes
from .theme import STYLE
from .image_view import ImageView
from .overlay import OverlayControls
from .center_detail import CenterDetail,SquareImagePanel
from .analysis_panel import AnalysisPanel,AXES
from .records_panel import RecordsPanel
from fistar.storage.repository import connect_database,save_measurement,get_limits,set_limits
from fistar.core.models import Limits,Calibration,Point

class WorkerSignals(QObject):
    finished=Signal(int,str,object,str)

class DetectionWorker(QRunnable):
    def __init__(self,revision,image_hash,values,hub,settings):
        super().__init__(); self.revision=revision; self.image_hash=image_hash
        self.values=values; self.hub=hub; self.settings=settings; self.signals=WorkerSignals()
    def run(self):
        try:
            result=detect_spokes(self.values,self.hub,self.settings); error=''
        except Exception as e: result=None; error=str(e)
        self.signals.finished.emit(self.revision,self.image_hash,result,error)

class MainWindow(QMainWindow):
    def __init__(self,database_path: Path | None=None):
        super().__init__(); self.setStyleSheet(STYLE);self.setWindowTitle('FiStar — スターショットQA'); self.resize(1000,700)
        self.session=AnalysisSession(); self.pool=QThreadPool(self); self._workers={}; self._discard_worker={}
        self._closing=False; self.detail_window=None;self._calibration_pick_active=False
        self._ruler_calibrating=False;self._ruler_original=None;self._ruler_pair=None;self._ruler_hash=None
        self.database_path=Path(database_path) if database_path else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))/'fistar-v1.sqlite'
        self.connection=connect_database(self.database_path)
        self.preferences=QSettings(str(self.database_path.parent/'fistar-preferences.ini'),QSettings.IniFormat)
        remembered=self.preferences.value('last_axis','gantry')
        if remembered in AXES:self.session.axis=remembered
        self.tabs=QTabWidget(); self.setCentralWidget(self.tabs)
        page=QWidget(); layout=QVBoxLayout(page);layout.setContentsMargins(12,10,12,8);layout.setSpacing(8);self.view=ImageView()
        file_box=QWidget();file_layout=QVBoxLayout(file_box);file_layout.setContentsMargins(6,6,6,6);file_layout.setSpacing(0)
        path_row=QHBoxLayout();path_row.setSpacing(10);self.path_edit=QLineEdit();self.path_edit.setMinimumWidth(220);self.path_edit.setMaximumWidth(340);self.path_edit.setPlaceholderText('TIFF画像パス');self.path_edit.returnPressed.connect(self.load_from_path)
        browse=QPushButton('参照');browse.setMinimumWidth(72);browse.clicked.connect(self.browse_image_path)
        self.open_button=QPushButton('開く');self.open_button.setMinimumWidth(72);self.open_button.setProperty('primary',True);self.open_button.clicked.connect(self.load_from_path)
        path_row.addWidget(self.path_edit,1);path_row.addWidget(browse);path_row.addWidget(self.open_button);path_row.addStretch();file_layout.addLayout(path_row)
        self.image_info=QLabel('TIFF画像を指定して開いてください');self.image_info.setWordWrap(True);self.image_info.setProperty('muted',True)
        icon_dir=Path(__file__).parent/'assets/icons/tools'
        self.pan_tool_button=QToolButton();self.reset_tool_button=QToolButton();self.ruler_tool_button=QToolButton()
        for button,name,text in ((self.pan_tool_button,'tools_hand.png','画像表示調節：ドラッグで移動、スクロールで拡大縮小'),(self.reset_tool_button,'tools_reset.png','画像全体を表示'),(self.ruler_tool_button,'tools_ruler.png','定規：2点で長さを測定。校正ボタンで既知長さから解像度を計算')):
            button.setIcon(QIcon(str(icon_dir/name)));button.setIconSize(QSize(24,24));button.setFixedSize(32,32);button.setToolTip(text);button.setAccessibleName(text);button.setAutoRaise(True)
        self.pan_tool_button.setCheckable(True);self.pan_tool_button.setChecked(True);self.pan_tool_button.clicked.connect(lambda:self.set_mode('pan'))
        self.reset_tool_button.clicked.connect(lambda:self.view.reset_view());self.ruler_tool_button.setCheckable(True);self.ruler_tool_button.clicked.connect(lambda:self.set_mode('ruler'))
        self.display_frame=QFrame();self.display_frame.setFrameShape(QFrame.StyledPanel);self.display_frame.setProperty('displayOptions',True)
        self.display_frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        display_layout=QVBoxLayout(self.display_frame);display_layout.setContentsMargins(6,4,6,4);display_layout.setSpacing(3)
        self.display_toggle=QToolButton();self.display_toggle.setText('表示する項目');self.display_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.display_toggle.setArrowType(Qt.RightArrow);self.display_toggle.setCheckable(True);self.display_toggle.setAutoRaise(True)
        display_layout.addWidget(self.display_toggle)
        self.overlay_controls=OverlayControls(self.view,columns=2,balanced=True)
        self.display_scroll=QScrollArea();self.display_scroll.setWidgetResizable(True);self.display_scroll.setWidget(self.overlay_controls)
        self.display_scroll.setFrameShape(QFrame.NoFrame);self.display_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.display_scroll.setFixedHeight(min(self.overlay_controls.sizeHint().height()+4,160))
        display_layout.addWidget(self.display_scroll);self.display_scroll.setVisible(False)
        def toggle_display(checked):
            self.display_scroll.setVisible(checked)
            self.display_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.display_toggle.toggled.connect(toggle_display)

        splitter=QSplitter();splitter.setHandleWidth(3);image_panel=QWidget();image_layout=QVBoxLayout(image_panel);image_layout.setContentsMargins(0,0,0,0)
        image_layout.setSpacing(6);image_layout.addWidget(file_box)
        self.panel=AnalysisPanel(self.session)
        old_resolution=self.panel.stage_boxes['calibration'];self.panel.layout().removeWidget(old_resolution)
        self.resolution_controls=QWidget();resolution_layout=QHBoxLayout(self.resolution_controls);resolution_layout.setContentsMargins(0,0,0,0);resolution_layout.setSpacing(6)
        resolution_layout.addWidget(QLabel('解像度'))
        self.panel.calibration_method.setMaximumWidth(140);resolution_layout.addWidget(self.panel.calibration_method)
        self.panel.pixel_length.setMaximumWidth(120);resolution_layout.addWidget(self.panel.numeric_frame)
        self.panel.stage_boxes['calibration']=self.resolution_controls
        old_resolution.layout().removeWidget(self.panel.calibration_label);old_resolution.hide()
        self.square_image=SquareImagePanel(self.view,alignment=Qt.AlignHCenter);self.square_image.setMinimumSize(160,160);self.view.setMinimumSize(64,64);image_layout.addWidget(self.square_image,1)
        tools_row=QHBoxLayout();tools_row.setSpacing(4)
        for button in (self.pan_tool_button,self.reset_tool_button,self.ruler_tool_button):tools_row.addWidget(button)
        tools_row.addStretch();tools_row.addSpacing(12);tools_row.addWidget(self.resolution_controls);image_layout.addLayout(tools_row)
        self.panel.calibration_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.ruler_bar=QWidget();ruler_layout=QHBoxLayout(self.ruler_bar);ruler_layout.setContentsMargins(0,0,0,0);ruler_layout.setSpacing(6)
        self.ruler_result=QLabel('画像上の2点を左クリックすると長さを測定します');self.ruler_result.setWordWrap(True);self.ruler_result.hide()
        self.ruler_calibrate=QPushButton('校正');self.ruler_calibrate.clicked.connect(self.begin_ruler_calibration);ruler_layout.addWidget(self.ruler_calibrate)
        self.ruler_known_frame=QWidget();known_layout=QHBoxLayout(self.ruler_known_frame);known_layout.setContentsMargins(0,0,0,0);known_layout.setSpacing(4)
        self.ruler_known=QLineEdit();self.ruler_known.setPlaceholderText('既知の長さ');self.ruler_known.setMaximumWidth(110);known_layout.addWidget(self.ruler_known);known_layout.addWidget(QLabel('mm'))
        self.ruler_cancel=QPushButton('中止');self.ruler_cancel.clicked.connect(lambda:self.set_mode('pan'));known_layout.addWidget(self.ruler_cancel);ruler_layout.addWidget(self.ruler_known_frame)
        self.ruler_known_frame.hide();self.ruler_bar.hide();tools_row.insertWidget(3,self.ruler_bar);image_layout.addWidget(self.ruler_result)
        self.panel.calibration_label.hide()
        self.operation_help=QLabel('ドラッグで移動、スクロールで拡大縮小、右クリックでレーザー基準点を指定');self.operation_help.setWordWrap(True);self.operation_help.setProperty('muted',True)
        image_layout.addWidget(self.operation_help);image_layout.addWidget(self.image_info);splitter.addWidget(image_panel)
        scroll=QScrollArea(); self.analysis_scroll=scroll;scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setWidget(self.panel)
        sidebar=QWidget();sidebar.setMinimumWidth(225);sidebar.setMaximumWidth(440);sidebar_layout=QVBoxLayout(sidebar);sidebar_layout.setContentsMargins(0,0,0,0);sidebar_layout.setSpacing(6)
        self.analysis_frame=QGroupBox('解析');self.analysis_frame.setObjectName('analysisFrame');analysis_layout=QVBoxLayout(self.analysis_frame);analysis_layout.setContentsMargins(3,3,3,3);analysis_layout.setSpacing(3);analysis_layout.addWidget(scroll)
        sidebar_layout.addWidget(self.analysis_frame,1);sidebar_layout.addWidget(self.display_frame);splitter.addWidget(sidebar)
        splitter.setStretchFactor(0,2);splitter.setStretchFactor(1,1);splitter.setSizes([510,255]); layout.addWidget(splitter,1)
        self.tabs.addTab(page,'解析')
        self.records=RecordsPanel(self.connection)
        records_scroll=QScrollArea();records_scroll.setWidgetResizable(True);records_scroll.setWidget(self.records);self.tabs.addTab(records_scroll,'記録')
        settings_page=QWidget();settings_layout=QVBoxLayout(settings_page)
        settings_layout.addWidget(QLabel('装置・回転軸の許容値'))
        settings_note=QLabel('解析タブで選択した装置と回転軸の許容値を設定します。交点重心方式は合否判定しません。');settings_note.setWordWrap(True);settings_layout.addWidget(settings_note)
        settings_button=QPushButton('現在の装置・軸の許容値を設定');settings_button.clicked.connect(self.edit_limits);settings_layout.addWidget(settings_button);settings_layout.addStretch()
        self.tabs.addTab(settings_page,'設定')
        self.records.reopen_requested.connect(self.reopen_record)
        self.statusBar().showMessage(f'記録の保存先：{self.database_path}')
        self.panel.identity_requested.connect(self.change_identity)
        self.panel.calibration_requested.connect(self.change_calibration)
        self.panel.mode_requested.connect(self.set_mode)
        self.panel.detect_requested.connect(self.detect)
        self.panel.detection_settings_requested.connect(self.change_detection_settings)
        self.panel.spoke_requested.connect(lambda spoke:self.perform(lambda:self.session.replace_spoke(spoke)))
        self.panel.selected_requested.connect(self.select_spoke)
        self.panel.center_method_requested.connect(lambda method:self.perform(lambda:self.session.set_center_method(method)))
        self.panel.detail_requested.connect(self.open_center_detail)
        self.panel.save_requested.connect(self.save)
        self.panel.limits_requested.connect(self.edit_limits)
        self.view.laser_selected.connect(lambda point:self.perform(lambda:self.session.set_laser(point)))
        self.view.calibration_selected.connect(self.finish_manual_calibration)
        self.view.ruler_selected.connect(self.finish_ruler)
        self.view.view_changed.connect(self.update_ruler_result)
        self.refresh()
    def perform(self,action):
        try: action()
        except Exception as e: self.show_error(str(e))
        self.refresh()
    def show_error(self,error): QMessageBox.warning(self,'操作を完了できません',error)
    def confirm_stage(self,step):
        try: self.session.confirm_step(step)
        except Exception as error: self.show_error(str(error))
        else:
            if step=='laser': self.set_mode('pan')
        self.refresh()
    def set_mode(self,mode):
        mode=mode or 'pan'
        if mode!='ruler' and self._ruler_calibrating:self.cancel_ruler_calibration()
        if mode=='calibration' and self.session.image:
            self._calibration_pick_active=True
            self.session.set_calibration(self.session.calibration,'manual','画像上で2点を指定してください')
            self.refresh()
        elif self._calibration_pick_active:
            self._calibration_pick_active=False
            if self.session.calibration_mode=='manual' and self.session.calibration is not None and self.session.calibration_error:
                self.session.set_calibration(self.session.calibration,'manual');self.refresh()
        self.view.set_mode(mode)
        self.pan_tool_button.blockSignals(True);self.pan_tool_button.setChecked(mode in ('pan','laser'));self.pan_tool_button.blockSignals(False)
        self.ruler_tool_button.blockSignals(True);self.ruler_tool_button.setChecked(mode=='ruler');self.ruler_tool_button.blockSignals(False)
        self.ruler_bar.setVisible(mode=='ruler');self.ruler_result.setVisible(mode=='ruler')
        if mode=='ruler':
            self.operation_help.hide();self.update_ruler_result();return
        self.operation_help.show()
        self.operation_help.setText('校正用の2点を画像上で左クリックしてください' if mode=='calibration' else 'ドラッグで移動、スクロールで拡大縮小、右クリックでレーザー基準点を指定')
    def refresh(self):
        self.view.set_session(self.session); self.panel.refresh(self.current_limits())
        self.panel.calibration_label.hide()
        if self._ruler_calibrating:self.panel.warnings.setText('解像度の校正中')
        self.panel.detect_button.setEnabled(self.session.can_detect and not self._workers)
        image=self.session.image
        if image:
            h,w=image.raw.shape[:2]
            c=self.session.calibration
            resolution=f'解像度 X {c.sx_mm:.8g}, Y {c.sy_mm:.8g} mm/px' if c else '未校正（px）'
            self.image_info.setText(f'表示中：{image.path.name} ／ {w}×{h} px ／ {image.raw.dtype.itemsize*8} bit ／ {resolution}')
            if not self.path_edit.hasFocus():self.path_edit.setText(str(image.path))
        else:self.image_info.setText('TIFF画像を指定して開いてください')
        self.ruler_tool_button.setEnabled(image is not None)
        if image and self._ruler_hash!=image.sha256:self._ruler_pair=None;self._ruler_hash=image.sha256
        self.update_ruler_result()
        self.sync_detail()
    def sync_detail(self):
        if self.detail_window and self.detail_window.isVisible():
            if (self.session.requires_redetection or self.session.calibration_error) and self.session.dirty:self.detail_window.close()
            else:self.detail_window.sync(self.view)
    def open_center_detail(self):
        if not self.session.result or self.session.result.selected is None: return
        if self.detail_window is None: self.detail_window=CenterDetail(self)
        self.detail_window.image_key=None
        self.detail_window.sync(self.view); self.detail_window.show(); self.detail_window.center_on_result()
        self.detail_window.raise_(); self.detail_window.activateWindow()
    def change_identity(self,device,axis):
        self.preferences.setValue('last_axis',axis);self.preferences.sync()
        self.perform(lambda:self.session.set_identity(device,axis))
    def change_detection_settings(self,settings):
        previous=self.session.detection_settings
        if previous is None or previous.radius_ratio!=settings.radius_ratio:
            self.overlay_controls.checks['search_circle'].setChecked(True)
        self.perform(lambda:self.session.set_detection_settings(settings))
    def current_limits(self):
        return get_limits(self.connection,self.session.device,self.session.axis)
    def allow_discard(self):
        if not self.session.dirty: return True
        box=QMessageBox(self); box.setWindowTitle('未保存の解析'); box.setText('解析に未保存の変更があります。')
        save=box.addButton('保存',QMessageBox.AcceptRole); discard=box.addButton('破棄',QMessageBox.DestructiveRole); cancel=box.addButton('キャンセル',QMessageBox.RejectRole)
        save.setEnabled(self.session.ready_for_review); box.setDefaultButton(cancel); box.exec()
        if box.clickedButton()==save: return self.save()
        return box.clickedButton()==discard
    def browse_image_path(self):
        path,_=QFileDialog.getOpenFileName(self,'フィルムTIFFを選択',self.path_edit.text(),'TIFF (*.tif *.tiff)')
        if path:
            self.path_edit.setText(path)
            self.load_from_path()
    def load_from_path(self):
        path=self.path_edit.text().strip().strip('"').strip("'")
        if not path:self.show_error('TIFF画像パスを指定してください');return
        try:image=load_tiff(Path(path).expanduser())
        except Exception as error:self.show_error(str(error));return
        if not self.allow_discard():return
        device=self.panel.device.text().strip() or 'temp'
        self.cancel_ruler_calibration();self._ruler_pair=None;self.view.ruler_points=()
        self.session.set_image(image);self.session.device=device
        axis=self.preferences.value('last_axis','gantry')
        self.session.axis=axis if axis in AXES else 'gantry'
        self.panel.pixel_length.blockSignals(True);self.panel.pixel_length.clear();self.panel.pixel_length.blockSignals(False)
        self.set_mode('pan');self.refresh()
    def open_image(self):self.browse_image_path()
    def confirm_edits_discard(self):
        if not any(s.origin=='manual' for s in self.session.spokes): return True
        return QMessageBox.question(self,'手動修正の破棄','この操作で手動修正した帯を破棄します。続けますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
    def change_calibration(self,action):
        if not self.session.image:return
        if self._ruler_calibrating:self.cancel_ruler_calibration()
        def apply():
            if action=='none':self.session.set_calibration(None,'none')
            elif action=='tag':
                c=self.session.image.tagged_calibration
                self.session.set_calibration(c,'tag','TIFFに利用可能な解像度タグがありません。他の校正方法を選んでください' if c is None else '')
            elif action=='numeric':
                try:
                    spacing=float(self.panel.pixel_length.text())
                    if not math.isfinite(spacing) or spacing<=0:raise ValueError()
                except ValueError:self.session.set_calibration(None,'numeric','正の数値をmm/pxで入力してください')
                else:self.session.set_calibration(Calibration(spacing,spacing,'入力値'),'numeric')
            elif action=='manual':
                c=self.session.calibration
                if c and c.reference:
                    a,b,_=c.reference;self.session.set_calibration(manual_calibration(a,b,self.panel.known_length.value()),'manual')
                else:self.session.set_calibration(None,'manual','既知長さを入力し「画像上の2点を指定」で校正してください')
        self.perform(apply)
        if action!='manual':self.set_mode('pan')
    def finish_manual_calibration(self,a,b):
        self.perform(lambda:self.session.set_calibration(manual_calibration(a,b,self.panel.known_length.value()),'manual'))
        if not self.session.calibration_error:self.set_mode('pan')
    def begin_ruler_calibration(self):
        if not self.session.image:return
        if not self._ruler_calibrating:
            self._ruler_original=(self.session.calibration,self.session.calibration_mode,self.session.calibration_error)
        self._ruler_calibrating=True;self._ruler_pair=None;self.view.ruler_points=();self.view.set_mode('ruler')
        self.ruler_known_frame.show();self.ruler_known.clear();self.ruler_known.setFocus()
        self.session.set_calibration(self.session.calibration,self.session.calibration_mode,'既知の長さをmmで入力し、画像上の2点を指定してください')
        self.refresh()
    def cancel_ruler_calibration(self):
        if not self._ruler_calibrating:return
        c,mode,error=self._ruler_original;self._ruler_calibrating=False;self._ruler_original=None;self.ruler_known_frame.hide()
        self.session.set_calibration(c,mode,error);self.refresh()
    def finish_ruler(self,a,b):
        distance=math.hypot(b.x-a.x,b.y-a.y)
        if distance<=1e-12:
            self._ruler_pair=None
            self.ruler_result.setText('異なる2点を指定してください');return
        if self._ruler_calibrating:
            try:
                length=float(self.ruler_known.text());c=manual_calibration(a,b,length)
            except ValueError:
                self.ruler_result.setText('正の既知長さをmmで入力し、2点を指定し直してください');return
            self._ruler_calibrating=False;self._ruler_original=None;self.ruler_known_frame.hide()
            self.session.set_calibration(c,'manual');self._ruler_pair=(a,b);self.refresh()
            self.ruler_result.setText(f'校正：{c.sx_mm:.8g} mm/px ／ 測定 {length:.6g} mm ({distance:.6g} px)')
        else:self._ruler_pair=(a,b);self.update_ruler_result()
    def update_ruler_result(self):
        if len(self.view.ruler_points)==1:
            self._ruler_pair=None;self.ruler_result.setText('画像上の2点目を左クリックしてください');return
        if self._ruler_calibrating:
            self.ruler_result.setText('既知長さをmmで入力し、画像上の2点を左クリックしてください');return
        if not self._ruler_pair:
            self.ruler_result.setText('画像上の2点を左クリックして測定します。既知長さで校正する場合は「校正」を押してください。');return
        a,b=self._ruler_pair;dx=b.x-a.x;dy=b.y-a.y;distance=math.hypot(dx,dy);c=self.session.calibration
        self.ruler_result.setText(f'{distance:.6g} px'+(f' ／ {math.hypot(dx*c.sx_mm,dy*c.sy_mm):.6g} mm' if c and not self.session.calibration_error else '（未校正）'))
    def detect(self,settings):
        s=self.session
        self.panel._identity()
        if not s.can_detect or self._workers:
            self.show_error(s.readiness_message or '検出処理中です');return
        if not self.confirm_edits_discard(): return
        s.set_detection_settings(settings)
        worker=DetectionWorker(s.revision,s.image.sha256,analysis_channel(s.image),s.laser,settings)
        token=s.revision; self._workers[token]=worker; self._discard_worker[token]=True
        worker.signals.finished.connect(self.detection_finished)
        self.set_mode('pan')
        self.statusBar().showMessage('照射帯を検出しています…'); self.panel.detect_button.setEnabled(False)
        self.pool.start(worker)
    def detection_finished(self,revision,image_hash,result,error):
        self._workers.pop(revision,None); discard=self._discard_worker.pop(revision,False)
        if self._closing: return
        s=self.session
        if s.revision!=revision or not s.image or s.image.sha256!=image_hash:
            self.refresh();self.statusBar().showMessage('前の状態の検出結果を適用しませんでした'); return
        if error: self.show_error(error)
        else: s.apply_detection(revision,image_hash,result,discard)
        self.refresh()
        if not error:QTimer.singleShot(0,self.reveal_results)
        self.statusBar().showMessage('検出できませんでした。設定を変更して再検出してください' if error else '検出完了。画像と結果を確認して保存してください')
    def reveal_results(self):
        if not self._closing:self.analysis_scroll.ensureWidgetVisible(self.panel.save_button)
    def select_spoke(self,spoke_id):
        self.view.selected_id=spoke_id; self.view.draw_overlay()
        self.panel.spoke_list.blockSignals(True)
        for i in range(self.panel.spoke_list.count()):
            item=self.panel.spoke_list.item(i)
            if item.data(Qt.UserRole)==spoke_id: self.panel.spoke_list.setCurrentItem(item)
        self.panel.spoke_list.blockSignals(False)
    def save(self):
        try:
            self.panel._identity()
            self.session.confirm_step('result')
            record=self.session.measurement(self.current_limits())
            save_measurement(self.connection,record)
        except Exception as e:
            self.show_error(str(e)); return False
        self.session.dirty=False; self.refresh(); self.records.refresh()
        self.statusBar().showMessage(f'保存しました：{record.image_name} ／ {self.database_path}')
        return True
    def edit_limits(self):
        self.panel._identity()
        if not self.session.device:
            self.show_error('装置名を入力してください'); return
        old=self.current_limits(); dialog=QDialog(self); dialog.setWindowTitle('装置・軸の許容値')
        form=QFormLayout(dialog); form.addRow(QLabel(f'{self.session.device} ／ {self.panel.axis.currentText()}'))
        unit=QComboBox(); unit.addItems(['mm','px']); unit.setCurrentText(old.unit); form.addRow('単位',unit)
        radius=QLineEdit('' if old.radius is None else str(old.radius)); delta=QLineEdit('' if old.laser_distance is None else str(old.laser_distance))
        form.addRow('半径の上限',radius); form.addRow('レーザー偏位の上限',delta); form.addRow(QLabel('空欄は未設定。保存済み記録は変更しません。'))
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def accept():
            try:
                value=Limits(unit.currentText(),float(radius.text()) if radius.text().strip() else None,float(delta.text()) if delta.text().strip() else None)
                set_limits(self.connection,self.session.device,self.session.axis,value)
            except Exception as e: self.show_error(str(e)); return
            self.session._change('result'); dialog.accept()
        buttons.accepted.connect(accept); dialog.exec(); self.refresh()
    def reopen_record(self,record):
        try:
            image=load_tiff(Path(record.snapshot['image_path']))
            if image.sha256!=record.snapshot['image_sha256']: raise ValueError('元画像の内容が保存時と異なります')
            session=AnalysisSession(); session.restore(image,record)
        except Exception as e: self.show_error(str(e)); return
        if not self.allow_discard(): return
        # Keep the monotonic revision so a pending worker cannot overwrite the restored record.
        session.revision=self.session.revision+1
        self.cancel_ruler_calibration();self._ruler_pair=None;self.view.ruler_points=()
        self.session=session; self.panel.session=session
        self.panel.pixel_length.blockSignals(True);self.panel.pixel_length.setText(f'{session.calibration.sx_mm:.12g}' if session.calibration else '');self.panel.pixel_length.blockSignals(False)
        self.set_mode(None); self.refresh(); self.tabs.setCurrentIndex(0)
    def closeEvent(self,event):
        if self.allow_discard():
            if self.detail_window: self.detail_window.close()
            self._closing=True; self.pool.waitForDone(); self.connection.close(); event.accept()
        else: event.ignore()

def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('FiStar'); app.setOrganizationName('FiStar')
    window=MainWindow(); window.show()
    return app.exec()
