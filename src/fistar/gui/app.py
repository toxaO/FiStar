import sys
from pathlib import Path
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QStandardPaths,QSize
from PySide6.QtWidgets import (QApplication,QToolButton,QGroupBox,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QScrollArea,QTabWidget,QPushButton,QLabel,QFileDialog,QMessageBox,QDialog,QFormLayout,QComboBox,QLineEdit,QDialogButtonBox,QDoubleSpinBox)
from PySide6.QtGui import QIcon
from fistar.core.imaging import load_tiff,analysis_channel,manual_calibration
from fistar.workflow.session import AnalysisSession
from fistar.core.detection import detect_spokes
from .image_view import ImageView
from .overlay import OverlayControls
from .center_detail import CenterDetail
from .analysis_panel import AnalysisPanel
from .records_panel import RecordsPanel
from fistar.storage.repository import connect_database,save_measurement,get_limits,set_limits,list_devices
from fistar.core.models import Limits

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
        super().__init__(); self.setWindowTitle('FiStar — スターショットQA'); self.resize(1320,900)
        self.session=AnalysisSession(); self.pool=QThreadPool(self); self._workers={}; self._discard_worker={}
        self._closing=False; self.detail_window=None
        self.database_path=Path(database_path) if database_path else Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))/'fistar-v1.sqlite'
        self.connection=connect_database(self.database_path)
        self.tabs=QTabWidget(); self.setCentralWidget(self.tabs)
        page=QWidget(); layout=QVBoxLayout(page)
        toolbar=QHBoxLayout()
        self.mode_label=QLabel('画像操作：画像移動')
        self.pan_tool_button=QToolButton(); self.reset_tool_button=QToolButton()
        icon_dir=Path(__file__).parent/'assets/icons/tools'
        for button,filename,label in ((self.pan_tool_button,'tools_hand.png','パン'),(self.reset_tool_button,'tools_reset.png','全体表示に戻す')):
            button.setIcon(QIcon(str(icon_dir/filename))); button.setIconSize(QSize(24,24)); button.setFixedSize(QSize(32,32))
            button.setToolTip(label); button.setAccessibleName(label); button.setAutoRaise(True); button.setFocusPolicy(Qt.NoFocus)
            toolbar.addWidget(button)
        self.pan_tool_button.setCheckable(True); self.pan_tool_button.setChecked(True)
        self.pan_tool_button.clicked.connect(lambda:self.toggle_navigation('pan'))
        self.reset_tool_button.clicked.connect(lambda:self.view.reset_view())
        toolbar.addWidget(self.mode_label)
        toolbar.addStretch()
        toolbar.addWidget(QLabel('表示下限／上限'))
        self.display_low=QDoubleSpinBox(); self.display_high=QDoubleSpinBox()
        for spin in (self.display_low,self.display_high):
            spin.setRange(-1e12,1e12); spin.setDecimals(1); spin.setMaximumWidth(105)
            spin.editingFinished.connect(self.change_display); toolbar.addWidget(spin)
        auto=QPushButton('表示を自動調整'); auto.clicked.connect(self.auto_display); toolbar.addWidget(auto)
        layout.addLayout(toolbar)
        splitter=QSplitter(); self.view=ImageView(); splitter.addWidget(self.view)
        self.panel=AnalysisPanel(self.session)
        display_box=QGroupBox('画像の表示'); display_box.setCheckable(True); display_box.setChecked(False)
        display_layout=QVBoxLayout(display_box); self.overlay_controls=OverlayControls(self.view)
        display_layout.addWidget(self.overlay_controls); self.overlay_controls.setVisible(False)
        display_box.toggled.connect(self.overlay_controls.setVisible)
        self.panel.layout().insertWidget(0,display_box)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.panel); scroll.setMinimumWidth(330); scroll.setMaximumWidth(470); splitter.addWidget(scroll)
        splitter.setSizes([900,390]); layout.addWidget(splitter)
        self.tabs.addTab(page,'解析')
        self.records=RecordsPanel(self.connection); self.tabs.addTab(self.records,'記録')
        self.records.reopen_requested.connect(self.reopen_record)
        self.statusBar().showMessage(f'記録の保存先：{self.database_path}')
        self.panel.open_requested.connect(self.open_image)
        self.panel.identity_requested.connect(lambda device,axis:self.perform(lambda:self.session.set_identity(device,axis)))
        self.panel.calibration_requested.connect(self.change_calibration)
        self.panel.mode_requested.connect(self.set_mode)
        self.panel.detect_requested.connect(self.detect)
        self.panel.spoke_requested.connect(lambda spoke:self.perform(lambda:self.session.replace_spoke(spoke)))
        self.panel.selected_requested.connect(self.select_spoke)
        self.panel.confirm_requested.connect(self.confirm_stage)
        self.panel.center_method_requested.connect(lambda method:self.perform(lambda:self.session.set_center_method(method)))
        self.panel.detail_requested.connect(self.open_center_detail)
        self.panel.save_requested.connect(self.save)
        self.panel.limits_requested.connect(self.edit_limits)
        self.view.laser_selected.connect(lambda point:self.perform(lambda:self.session.set_laser(point)))
        self.view.calibration_selected.connect(lambda a,b:self.perform(lambda:self.session.set_calibration(manual_calibration(a,b,self.panel.known_length.value()))))
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
    def toggle_navigation(self,mode):
        self.set_mode('pan')
    def set_mode(self,mode):
        mode=mode or 'pan'; self.view.set_mode(mode)
        self.pan_tool_button.blockSignals(True); self.pan_tool_button.setChecked(mode=='pan'); self.pan_tool_button.blockSignals(False)
        self.mode_label.setText('画像操作：'+{'pan':'画像移動','laser':'レーザー点指定（右クリック／左ドラッグで移動）','calibration':'校正用2点指定'}[mode])
    def refresh(self):
        self.view.set_session(self.session); self.panel.refresh(self.current_limits())
        self.panel.set_devices(list_devices(self.connection))
        self.display_low.setValue(self.view.display_low); self.display_high.setValue(self.view.display_high)
        self.sync_detail()
    def sync_detail(self):
        if self.detail_window and self.detail_window.isVisible(): self.detail_window.sync(self.view)
    def open_center_detail(self):
        if not self.session.result or self.session.result.selected is None: return
        if self.detail_window is None: self.detail_window=CenterDetail(self)
        self.detail_window.image_key=None
        self.detail_window.sync(self.view); self.detail_window.show(); self.detail_window.center_on_result()
        self.detail_window.raise_(); self.detail_window.activateWindow()
    def change_display(self):
        try: self.view.set_display_range(self.display_low.value(),self.display_high.value()); self.sync_detail()
        except ValueError as e: self.show_error(str(e))
    def auto_display(self):
        self.view.auto_display(); self.display_low.setValue(self.view.display_low); self.display_high.setValue(self.view.display_high); self.sync_detail()
    def current_limits(self):
        return get_limits(self.connection,self.session.device,self.session.axis)
    def allow_discard(self):
        if not self.session.dirty: return True
        box=QMessageBox(self); box.setWindowTitle('未保存の解析'); box.setText('解析に未保存の変更があります。')
        save=box.addButton('保存',QMessageBox.AcceptRole); discard=box.addButton('破棄',QMessageBox.DestructiveRole); cancel=box.addButton('キャンセル',QMessageBox.RejectRole)
        save.setEnabled(self.session.can_save); box.setDefaultButton(cancel); box.exec()
        if box.clickedButton()==save: return self.save()
        return box.clickedButton()==discard
    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,'フィルムTIFFを選択','','TIFF (*.tif *.tiff)')
        if not path: return
        try: image=load_tiff(Path(path))
        except Exception as e: self.show_error(str(e)); return
        if not self.allow_discard(): return
        self.session.set_image(image); self.set_mode(None); self.refresh()
    def confirm_edits_discard(self):
        if not any(s.origin=='manual' for s in self.session.spokes): return True
        return QMessageBox.question(self,'手動修正の破棄','この操作で手動修正した帯を破棄します。続けますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
    def change_calibration(self,action):
        if not self.session.image: return
        if action=='manual': self.set_mode('calibration')
        elif action=='tag': self.perform(lambda:self.session.set_calibration(self.session.image.tagged_calibration))
        else: self.perform(lambda:self.session.set_calibration(None))
    def detect(self,settings):
        s=self.session
        if not s.image or not s.laser or not all(k in s.confirmed_steps for k in s.steps[:4]):
            self.show_error('レーザー基準点までの確認を先に完了してください'); return
        if not self.confirm_edits_discard(): return
        s.set_detection_settings(settings)
        worker=DetectionWorker(s.revision,s.image.sha256,analysis_channel(s.image),s.laser,settings)
        token=s.revision; self._workers[token]=worker; self._discard_worker[token]=True
        worker.signals.finished.connect(self.detection_finished)
        self.statusBar().showMessage('照射帯を検出しています…'); self.panel.detect_button.setEnabled(False)
        self.pool.start(worker)
    def detection_finished(self,revision,image_hash,result,error):
        self._workers.pop(revision,None); discard=self._discard_worker.pop(revision,False)
        if self._closing: return
        s=self.session
        if s.revision!=revision or not s.image or s.image.sha256!=image_hash:
            self.statusBar().showMessage('前の状態の検出結果を適用しませんでした'); return
        if error: self.show_error(error)
        else: s.apply_detection(revision,image_hash,result,discard)
        self.refresh(); self.statusBar().showMessage('検出できませんでした。設定を変更して再検出してください' if error else '検出完了。帯の本数・中心線を確認してください')
    def select_spoke(self,spoke_id):
        self.view.selected_id=spoke_id; self.view.draw_overlay()
        self.panel.spoke_list.blockSignals(True)
        for i in range(self.panel.spoke_list.count()):
            item=self.panel.spoke_list.item(i)
            if item.data(Qt.UserRole)==spoke_id: self.panel.spoke_list.setCurrentItem(item)
        self.panel.spoke_list.blockSignals(False)
    def save(self):
        try:
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
        self.session=session; self.panel.session=session
        self.set_mode(None); self.refresh(); self.tabs.setCurrentIndex(0)
    def closeEvent(self,event):
        if self.allow_discard():
            if self.detail_window: self.detail_window.close()
            self._closing=True; self.pool.waitForDone(); self.connection.close(); event.accept()
        else: event.ignore()

def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('FiStar'); app.setOrganizationName('FiStar')
    app.setStyleSheet('QWidget {font-size: 13px;} QGroupBox {font-weight: 600; margin-top: 14px; padding-top: 12px;} QPushButton {padding: 6px;}')
    window=MainWindow(); window.show()
    return app.exec()
