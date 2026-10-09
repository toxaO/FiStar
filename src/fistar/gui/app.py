import sys
import math
from sqlite3 import Error as SQLiteError
from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QStandardPaths,QSize,QSettings,QTimer
from PySide6.QtWidgets import (QApplication,QToolButton,QGroupBox,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QScrollArea,QTabWidget,QPushButton,QLabel,QFileDialog,QMessageBox,QDialog,QFormLayout,QComboBox,QLineEdit,QDialogButtonBox,QDoubleSpinBox,QFrame,QSizePolicy,QStackedWidget,QListWidget)
from PySide6.QtGui import QIcon
from fistar.core.imaging import load_tiff,analysis_channel,manual_calibration
from fistar.workflow.session import AnalysisSession
from fistar.core.detection import detect_spokes
from fistar.core.backend import prepare_backend
from fistar.storage.portable import portable_data_dir,save_with_reference,import_legacy
from .axis_settings import AxisSettings
from .theme import STYLE
from .image_view import ImageView
from .overlay import OverlayControls
from .center_detail import CenterDetail,SquareImagePanel
from .analysis_panel import AnalysisPanel,AXES
from .records_panel import RecordsPanel
from fistar.storage.repository import connect_database,save_measurement,list_devices,add_device,remove_device,list_axes
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

class PreparationSignals(QObject):
    finished=Signal(object,str)

class PreparationWorker(QRunnable):
    def __init__(self,cache_path):
        super().__init__();self.cache_path=cache_path;self.signals=PreparationSignals()
    def run(self):
        try:info=prepare_backend(self.cache_path);error=''
        except Exception as exc:info=None;error=str(exc)
        self.signals.finished.emit(info,error)

class MainWindow(QMainWindow):
    def __init__(self,database_path: Path | None=None,cache_path: Path | None=None):
        super().__init__(); self.setStyleSheet(STYLE);self.setWindowTitle('FiStar — スターショットQA');self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/fistar.ico'))); self.resize(1000,740)
        self.session=AnalysisSession(); self.pool=QThreadPool(self); self._workers={}; self._discard_worker={}
        self._closing=False; self.detail_window=None;self._calibration_pick_active=False
        self._ruler_calibrating=False;self._ruler_original=None;self._ruler_pair=None;self._ruler_hash=None
        self.database_path=Path(database_path) if database_path else portable_data_dir()/'fistar-v1.sqlite'
        self.cache_path=Path(cache_path) if cache_path else (self.database_path.parent/'cache' if database_path else Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)))
        self.backend_state='idle';self.backend_info=None;self._prepare_worker=None;self._pending_detection=None
        self.connection=connect_database(self.database_path)
        self.preferences=QSettings(str(self.database_path.parent/'fistar-preferences.ini'),QSettings.IniFormat)
        remembered=self.preferences.value('last_axis','gantry')
        axes=list_axes(self.connection);self.session.axis=remembered if remembered in [a['id'] for a in axes] else axes[0]['id']
        self.tabs=QTabWidget(); self.setCentralWidget(self.tabs)
        page=QWidget(); layout=QVBoxLayout(page);layout.setContentsMargins(12,10,12,8);layout.setSpacing(8);self.view=ImageView()
        file_box=QWidget();file_layout=QVBoxLayout(file_box);file_layout.setContentsMargins(6,6,6,6);file_layout.setSpacing(0)
        path_row=QHBoxLayout();path_row.setSpacing(10);self.path_edit=QLineEdit();self.path_edit.setMinimumWidth(220);self.path_edit.setMaximumWidth(340);self.path_edit.setPlaceholderText('TIFF画像パス');self.path_edit.returnPressed.connect(self.load_from_path)
        browse=QPushButton('参照');browse.setMinimumWidth(72);browse.clicked.connect(self.browse_image_path)
        self.open_button=QPushButton('開く');self.open_button.setMinimumWidth(72);self.open_button.setProperty('primary',True);self.open_button.clicked.connect(self.load_from_path)
        self.path_edit.setText(str(self.preferences.value('last_image_path','')))
        path_row.addWidget(self.path_edit,1);path_row.addWidget(browse);path_row.addWidget(self.open_button);path_row.addStretch();file_layout.addLayout(path_row)
        self.image_info=QLabel('TIFF画像を指定して開いてください');self.image_info.setWordWrap(True);self.image_info.setProperty('muted',True)
        icon_dir=Path(__file__).parent/'assets/icons/tools'
        self.pan_tool_button=QToolButton();self.reset_tool_button=QToolButton();self.ruler_tool_button=QToolButton()
        for button,name,text in ((self.pan_tool_button,'tools_hand.png','画像表示調節：ドラッグで移動、スクロールで拡大縮小'),(self.reset_tool_button,'tools_reset.png','画像全体を表示'),(self.ruler_tool_button,'tools_ruler.png','定規：2点で長さを測定。校正ボタンで既知長さから解像度を計算')):
            button.setProperty('imageTool',True);button.setIcon(QIcon(str(icon_dir/name)));button.setIconSize(QSize(24,24));button.setFixedSize(32,32);button.setToolTip(text);button.setAccessibleName(text);button.setAutoRaise(True)
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
        self.square_image=SquareImagePanel(self.view,alignment=Qt.AlignHCenter);self.square_image.setMinimumSize(160,160);self.view.setMinimumSize(64,64);image_layout.addWidget(self.square_image,1)
        self.tools_frame=QFrame();self.tools_frame.setObjectName('stableImageTools');tools_layout=QVBoxLayout(self.tools_frame);tools_layout.setContentsMargins(6,4,6,3);tools_layout.setSpacing(2)
        tools_row=QHBoxLayout();tools_row.setSpacing(4)
        for button in (self.pan_tool_button,self.reset_tool_button,self.ruler_tool_button):tools_row.addWidget(button)
        tools_row.addStretch();tools_layout.addLayout(tools_row)
        self.panel.calibration_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.ruler_bar=QWidget();ruler_layout=QHBoxLayout(self.ruler_bar);ruler_layout.setContentsMargins(0,0,0,0);ruler_layout.setSpacing(4)
        self.ruler_result=QLabel('画像上の2点を左クリックすると長さを測定します');self.ruler_result.setWordWrap(True);self.ruler_result.setProperty('muted',True);self.ruler_result.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.ruler_calibrate=QPushButton('校正');self.ruler_calibrate.setFixedWidth(44);self.ruler_calibrate.clicked.connect(self.begin_ruler_calibration);ruler_layout.addWidget(self.ruler_calibrate)
        self.ruler_known_frame=QWidget();known_layout=QHBoxLayout(self.ruler_known_frame);known_layout.setContentsMargins(0,0,0,0);known_layout.setSpacing(4)
        self.ruler_known=QLineEdit();self.ruler_known.setPlaceholderText('既知の長さ');self.ruler_known.setFixedWidth(86);known_layout.addWidget(self.ruler_known);known_layout.addWidget(QLabel('mm'))
        self.ruler_cancel=QPushButton('中止');self.ruler_cancel.setFixedWidth(44);self.ruler_cancel.clicked.connect(lambda:self.set_mode('pan'));known_layout.addWidget(self.ruler_cancel);ruler_layout.addWidget(self.ruler_known_frame)
        for retained in (self.ruler_bar,self.ruler_known_frame,self.panel.numeric_frame):
            policy=retained.sizePolicy();policy.setRetainSizeWhenHidden(True);retained.setSizePolicy(policy)
        self.ruler_known_frame.hide();self.ruler_bar.hide();tools_row.insertWidget(3,self.ruler_bar)
        self.panel.calibration_label.hide()
        self.operation_help=QLabel('ドラッグで移動、スクロールで拡大縮小');self.operation_help.setWordWrap(True);self.operation_help.setProperty('muted',True)
        self.operation_help.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.tool_message=QStackedWidget();self.tool_message.addWidget(self.operation_help);self.tool_message.addWidget(self.ruler_result);tools_layout.addWidget(self.tool_message)
        image_layout.addWidget(self.tools_frame);image_layout.addWidget(self.image_info);self.image_info.setAlignment(Qt.AlignTop|Qt.AlignLeft);splitter.addWidget(image_panel)
        scroll=QScrollArea(); self.analysis_scroll=scroll;scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setWidget(self.panel)
        sidebar=QWidget();sidebar.setMinimumWidth(300);sidebar.setMaximumWidth(460);sidebar_layout=QVBoxLayout(sidebar);sidebar_layout.setContentsMargins(0,0,0,0);sidebar_layout.setSpacing(6)
        self.analysis_frame=QGroupBox('解析');self.analysis_frame.setObjectName('analysisFrame');analysis_layout=QVBoxLayout(self.analysis_frame);analysis_layout.setContentsMargins(3,3,3,3);analysis_layout.setSpacing(3);analysis_layout.addWidget(scroll)
        sidebar_layout.addWidget(self.analysis_frame,1);sidebar_layout.addWidget(self.display_frame);splitter.addWidget(sidebar)
        splitter.setStretchFactor(0,5);splitter.setStretchFactor(1,3);splitter.setSizes([650,400]); layout.addWidget(splitter,1)
        self.tabs.addTab(page,'解析')
        self.records=RecordsPanel(self.connection)
        records_scroll=QScrollArea();records_scroll.setWidgetResizable(True);records_scroll.setWidget(self.records);self.tabs.addTab(records_scroll,'記録')
        settings_page=QWidget();settings_layout=QVBoxLayout(settings_page)
        device_frame=QGroupBox('装置名の登録・削除');device_frame.setMaximumWidth(350)
        device_layout=QVBoxLayout(device_frame);device_layout.setContentsMargins(10,8,10,10);device_layout.setSpacing(8)
        device_entry_row=QHBoxLayout();self.device_name_entry=QLineEdit();self.device_name_entry.setPlaceholderText('追加する装置名');self.device_name_entry.returnPressed.connect(self.add_device_name)
        device_add=QPushButton('追加');device_add.clicked.connect(self.add_device_name);device_entry_row.addWidget(self.device_name_entry,1);device_entry_row.addWidget(device_add);device_layout.addLayout(device_entry_row)
        self.device_registry=QListWidget();self.device_registry.setFixedHeight(160);device_layout.addWidget(self.device_registry)
        device_delete=QPushButton('選択した装置名を削除');device_delete.clicked.connect(self.delete_device_name);device_layout.addWidget(device_delete)
        settings_note=QLabel('装置名は文字列で識別します。リストから削除しても過去の解析記録は残ります。');settings_note.setWordWrap(True);device_layout.addWidget(settings_note)
        settings_row=QHBoxLayout();settings_row.addWidget(device_frame)
        self.axis_settings=AxisSettings(self.connection);self.axis_settings.changed.connect(self.axes_changed);settings_row.addWidget(self.axis_settings);settings_row.addStretch();settings_layout.addLayout(settings_row);settings_layout.addStretch()
        self.refresh_device_names()
        self.tabs.addTab(settings_page,'設定')
        self.backend_retry=QPushButton('解析準備を再試行');self.backend_retry.clicked.connect(self.start_backend_preparation);self.backend_retry.hide();self.statusBar().addPermanentWidget(self.backend_retry)
        import_button=QPushButton('旧記録を取り込む');import_button.clicked.connect(self.import_old_records);settings_layout.insertWidget(settings_layout.count()-1,import_button,0,Qt.AlignLeft)
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
        self.view.laser_selected.connect(lambda point:self.perform(lambda:self.session.set_laser(point)))
        self.view.laser_selection_finished.connect(lambda:self.set_mode('pan'))
        self.view.calibration_selected.connect(self.finish_manual_calibration)
        self.view.ruler_selected.connect(self.finish_ruler)
        self.view.view_changed.connect(self.update_ruler_result)
        for message in (self.operation_help,self.ruler_result,self.image_info):message.ensurePolished()
        line_height=max(self.operation_help.fontMetrics().lineSpacing(),self.ruler_result.fontMetrics().lineSpacing())
        self.tool_message.setFixedHeight(line_height+4)
        self.image_info.setFixedHeight(self.image_info.fontMetrics().lineSpacing()*2+4)
        self.refresh()
    def showEvent(self,event):
        super().showEvent(event)
        if self.backend_state=='idle':QTimer.singleShot(0,self.start_backend_preparation)
    def start_backend_preparation(self):
        if self._closing or self.backend_state in ('preparing','ready'):return
        self.backend_state='preparing';self.backend_retry.hide()
        self.statusBar().showMessage('解析機能を準備しています…')
        self._prepare_worker=PreparationWorker(self.cache_path)
        self._prepare_worker.signals.finished.connect(self.backend_prepared)
        self.pool.start(self._prepare_worker)
    def backend_prepared(self,info,error):
        self._prepare_worker=None
        if self._closing:return
        if error:
            self.backend_state='failed';self._pending_detection=None;self.backend_retry.show()
            self.statusBar().showMessage('解析準備に失敗しました：'+error);self.refresh();return
        self.backend_state='ready';self.backend_info=info;pending=self._pending_detection;self._pending_detection=None
        self.refresh()
        if pending:
            revision,inputs,settings=pending
            if revision==self.session.revision and inputs==self.session.detection_inputs:self._launch_detection(settings);return
            self.statusBar().showMessage('準備中に条件が変わりました。照射帯を再度検出してください。')
        else:self.statusBar().showMessage('解析機能の準備ができました。' if info.persistent else '解析機能の準備ができました（一時キャッシュを使用）。')
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
        self.panel.laser_button.blockSignals(True);self.panel.laser_button.setChecked(mode=='laser');self.panel.laser_button.blockSignals(False)
        self.view.set_mode(mode)
        self.pan_tool_button.blockSignals(True);self.pan_tool_button.setChecked(mode=='pan');self.pan_tool_button.blockSignals(False)
        self.ruler_tool_button.blockSignals(True);self.ruler_tool_button.setChecked(mode=='ruler');self.ruler_tool_button.blockSignals(False)
        self.ruler_bar.setVisible(mode=='ruler')
        self.tool_message.setCurrentWidget(self.ruler_result if mode=='ruler' else self.operation_help)
        if mode=='ruler':self.update_ruler_result();return
        self.operation_help.setText('校正用の2点を画像上で左クリックしてください' if mode=='calibration' else ('画像上を左クリックで基準点指定（操作後に解除）' if mode=='laser' else 'ドラッグで移動、スクロールで拡大縮小'))
    def refresh(self):
        self.panel.set_axes(list_axes(self.connection))
        axis=next((a for a in list_axes(self.connection) if a['id']==self.session.axis),None)
        self.session.axis_definition=axis or getattr(self.session,'axis_definition',{})
        self.panel.set_devices(list_devices(self.connection))
        self.view.set_session(self.session); self.panel.refresh()
        self.panel.calibration_label.hide()
        if self._ruler_calibrating:self.panel.warnings.setText('解像度の校正中')
        self.panel.detect_button.setEnabled(self.session.can_detect and not self._workers and self._pending_detection is None)
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
    def axes_changed(self):
        axes=list_axes(self.connection)
        if self.session.axis not in [a['id'] for a in axes]:self.change_identity(self.session.device,axes[0]['id'])
        self.refresh();self.records.refresh()
    def refresh_device_names(self):
        self.device_registry.clear();self.device_registry.addItems(list_devices(self.connection))
    def add_device_name(self):
        try:add_device(self.connection,self.device_name_entry.text())
        except ValueError as error:self.show_error(str(error));return
        self.device_name_entry.clear();self.refresh_device_names();self.refresh();self.records.refresh()
    def delete_device_name(self):
        item=self.device_registry.currentItem()
        if item is None:return
        name=item.text();remove_device(self.connection,name)
        self.refresh_device_names();self.refresh();self.records.refresh()
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
        device=self.panel.device.currentText().strip()
        self.cancel_ruler_calibration();self._ruler_pair=None;self.view.ruler_points=()
        self.session.set_image(image);self.session.device=device
        self.preferences.setValue('last_image_path',str(image.path.resolve()));self.preferences.sync()
        axis=self.preferences.value('last_axis','gantry')
        axes=list_axes(self.connection);self.session.axis=axis if axis in [a['id'] for a in axes] else axes[0]['id']
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
        if self.backend_state!='ready':
            self._pending_detection=(s.revision,s.detection_inputs,settings)
            self.start_backend_preparation();self.refresh()
            self.statusBar().showMessage('解析機能を準備しています。完了後に検出します…');return
        self._launch_detection(settings)
    def _launch_detection(self,settings):
        s=self.session
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
            record=self.session.measurement()
            record=save_with_reference(self.connection,record,self.session.image)
        except Exception as e:
            self.show_error(str(e)); return False
        self.session.dirty=False; self.refresh(); self.records.refresh()
        self.statusBar().showMessage(f'保存しました：{record.image_name} ／ {self.database_path}')
        return True
    def import_old_records(self):
        source,_=QFileDialog.getOpenFileName(self,'取り込む旧データベースを選択','','SQLite (*.sqlite *.sqlite3)')
        if not source:return
        if QMessageBox.question(self,'旧記録の取り込み','旧DBを変更せず、現在のdataへ記録と参考JPEGを取り込みます。続けますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            added,missing=import_legacy(self.connection,source);self.records.refresh()
            QMessageBox.information(self,'取り込み完了',f'{added}件取り込みました。参考画像なし：{missing}件。元DBは変更していません。')
        except Exception as error:self.show_error(str(error))
    def closeEvent(self,event):
        if self.allow_discard():
            if self.detail_window: self.detail_window.close()
            if self.records.reference_window:self.records.reference_window.close()
            self._closing=True;self._pending_detection=None; self.pool.waitForDone(); self.connection.close(); event.accept()
        else: event.ignore()

def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/fistar.ico')))
    app.setApplicationName('FiStar'); app.setOrganizationName('FiStar')
    try:window=MainWindow()
    except (OSError,SQLiteError) as error:
        QMessageBox.critical(None,'保存先を開けません',f'dataフォルダを開けません。書込み可能なフォルダへアプリ一式を移動してください。\n{error}');return 1
    window.show()
    return app.exec()
