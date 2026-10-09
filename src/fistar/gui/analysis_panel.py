from dataclasses import replace
from html import escape
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QLabel,QPushButton,QComboBox,QLineEdit,QFormLayout,QDoubleSpinBox,QListWidget,QListWidgetItem,QTableWidget,QTableWidgetItem,QHeaderView)
from fistar.core.models import DetectionSettings
from .hover_help import HoverHelp

AXES={'gantry':'ガントリ','collimator':'コリメータ','couch':'カウチ'}
METHODS={'intersection_centroid':'交点重心方式','minimax':'最小円方式'}

def result_table(rows):
    cells=[]
    for label,value in rows:
        label=escape(str(label));value=escape(str(value)).replace('\n','<br>')
        cells.append(f'<tr><td width="42%" bgcolor="#e5edf2"><b>{label}</b></td><td width="58%" bgcolor="#ffffff">{value}</td></tr>')
    return '<table width="100%" border="1" cellspacing="0" cellpadding="5" style="border-color:#d7e2e8;">'+''.join(cells)+'</table>'

class AnalysisPanel(QWidget):
    identity_requested=Signal(str,str)
    calibration_requested=Signal(str)
    mode_requested=Signal(str)
    detect_requested=Signal(object)
    detection_settings_requested=Signal(object)
    spoke_requested=Signal(object)
    selected_requested=Signal(str)
    center_method_requested=Signal(str)
    detail_requested=Signal()
    save_requested=Signal()
    def __init__(self,session):
        super().__init__();self.setObjectName('analysisPanel');self.setAttribute(Qt.WA_StyledBackground,True); self.session=session;self.confirm_buttons={};self.stage_boxes={}
        root=QVBoxLayout(self);root.setContentsMargins(4,0,4,4);root.setSpacing(12)
        def group(title,key):
            box=QGroupBox(title);layout=QVBoxLayout(box);layout.setContentsMargins(5,4,5,4);layout.setSpacing(5);root.addWidget(box);self.stage_boxes[key]=box;return layout
        layout=group('1  装置と回転軸','identity')
        self.device=QComboBox();self.device.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);self.device.setMinimumContentsLength(10);self.device.setEditable(True);self.device.setInsertPolicy(QComboBox.NoInsert);self.device.addItem('', '')
        self.axis=QComboBox()
        for value,label in AXES.items():self.axis.addItem(label,value)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.addRow('装置名',self.device);form.addRow('回転軸',self.axis);layout.addLayout(form)
        self.device.currentTextChanged.connect(self._identity);self.axis.currentIndexChanged.connect(self._identity)
        layout=group('3  解像度','calibration')
        self.calibration_method=QComboBox()
        for label,value in [('未校正','none'),('TIFFタグ','tag'),('入力値','numeric')]:self.calibration_method.addItem(label,value)
        self.pixel_length=QLineEdit();self.pixel_length.setPlaceholderText('例：0.1');self.pixel_length.setToolTip('1pxあたりの長さをmmで入力します。正の有限値を指定してください。')
        self.numeric_frame=QWidget();numeric_layout=QHBoxLayout(self.numeric_frame);numeric_layout.setContentsMargins(0,0,0,0);numeric_layout.setSpacing(6)
        numeric_layout.addWidget(self.pixel_length,1);numeric_layout.addWidget(QLabel('mm/px'))
        calibration_row=QHBoxLayout();calibration_row.setSpacing(8);calibration_row.addWidget(self.calibration_method);calibration_row.addWidget(self.numeric_frame,1);layout.addLayout(calibration_row)
        self.calibration_label=QLabel();self.calibration_label.setWordWrap(True);layout.addWidget(self.calibration_label)
        # Retain the old reference-length value only for loading existing records.
        self.known_length=QDoubleSpinBox(self);self.known_length.hide();self.known_length.setRange(.001,10000);self.known_length.setValue(10)
        self.calibration_method.currentIndexChanged.connect(lambda:self.calibration_requested.emit(self.calibration_method.currentData()))
        self.pixel_length.textEdited.connect(lambda:self.calibration_requested.emit('numeric'))
        laser_layout=group('2  レーザー基準点','laser')
        self.laser_step=QLabel('未指定（基準点選択ボタンで指定）');self.laser_step.setWordWrap(True);laser_layout.addWidget(self.laser_step)
        self.laser_button=QPushButton('基準点選択');self.laser_button.setCheckable(True);self.laser_button.setProperty('laserSelection',True);self.laser_button.toggled.connect(lambda checked:self.mode_requested.emit('laser' if checked else 'pan'));laser_layout.addWidget(self.laser_button)
        root.removeWidget(self.stage_boxes['calibration']);root.addWidget(self.stage_boxes['calibration'])
        layout=group('4  照射帯の検出','spokes')
        detection_row=QHBoxLayout();detection_row.setSpacing(8);detection_left=QWidget();left_layout=QVBoxLayout(detection_left);left_layout.setContentsMargins(0,0,0,0);left_layout.setSpacing(8)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);self.radius=QDoubleSpinBox();self.peak_height=QDoubleSpinBox()
        self.radius.setRange(5,95);self.radius.setDecimals(1);self.radius.setSuffix(' %');self.radius.setValue(85)
        self.peak_height.setRange(.1,99.9);self.peak_height.setDecimals(1);self.peak_height.setSuffix(' %');self.peak_height.setValue(25)
        radius_tip='レーザー点から最も近い画像端までを100%とする探索円の半径です。円が帯を横切る位置に調整してください。'
        peak_tip='円周の最大ピークに対する採用下限（初期25%）です。低くすると薄い帯とノイズを拾いやすく、高くすると弱い帯を見落としやすくなります。'
        self.detection_help=[]
        for label,field,tip in [('探索円の半径',self.radius,radius_tip),('最小ピーク高さ',self.peak_height,peak_tip)]:
            text=QLabel(label);form.addRow(text,field)
            self.detection_help.append(HoverHelp((text,field),tip,self))
        left_layout.addLayout(form)
        self.radius.valueChanged.connect(self._settings_changed);self.peak_height.valueChanged.connect(self._settings_changed)
        self.detect_button=QPushButton('照射帯を検出');self.detect_button.setProperty('primary',True);self.detect_button.clicked.connect(self._detect);left_layout.addWidget(self.detect_button)
        self.warnings=QLabel();self.warnings.setWordWrap(True);left_layout.addWidget(self.warnings)
        self.spoke_list=QListWidget();self.spoke_list.setMinimumWidth(85);self.spoke_list.setMaximumWidth(115);self.spoke_list.setMinimumHeight(145);self.spoke_list.setMaximumHeight(220);self.spoke_list.itemChanged.connect(self._exclude)
        self.spoke_list.currentItemChanged.connect(lambda item,old:self.selected_requested.emit(item.data(Qt.UserRole)) if item else None);detection_row.addWidget(detection_left,1);detection_row.addWidget(self.spoke_list);layout.addLayout(detection_row)
        layout=group('5  結果の確認','result')
        self.center_method=QComboBox()
        for value,label in METHODS.items():self.center_method.addItem(label,value)
        self.center_method.currentIndexChanged.connect(lambda:self.center_method_requested.emit(self.center_method.currentData()));layout.addWidget(self.center_method)
        self.detail_button=QPushButton('中心付近を拡大');self.detail_button.clicked.connect(self.detail_requested.emit);layout.addWidget(self.detail_button)
        self.summary=QLabel();self.summary.setTextFormat(Qt.RichText);self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse);self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.result_label=QLabel();self.result_label.setTextFormat(Qt.RichText);self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse);self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
        self.save_button=QPushButton('結果を確認して保存');self.save_button.setProperty('primary',True);self.save_button.clicked.connect(self.save_requested.emit);root.addWidget(self.save_button);root.addStretch()
        for field,description in [
            (self.device,'装置名を手入力するか候補から選択します。空欄でも保存できます。'),
            (self.axis,'解析する回転軸を選択します。前回の選択を引き継ぎます。'),
            (self.calibration_method,'前回の解像度設定を引き継ぎます。TIFFタグは今回の画像から読み込みます。'),
            (self.laser_button,'左クリックで基準点を指定します。選択中はShift＋ドラッグで画像を移動できます。'),
            (self.detect_button,'現在の基準点と条件で照射帯を検出します。'),
            (self.spoke_list,'チェックを外すと帯を解析から除外します。'),
            (self.center_method,'同じ中心線を使い、交点重心方式または最小円方式で中心を求めます。'),
            (self.detail_button,'中心・レーザー点・交点を拡大して確認します。'),
            (self.save_button,'確認した結果と参考JPEGをdataへ保存します。')]:field.setToolTip(description)
    def _identity(self):self.identity_requested.emit(self.device.currentText(),self.axis.currentData())
    def settings(self):return DetectionSettings(self.radius.value()/100,self.peak_height.value()/100,'dark')
    def _settings_changed(self):self.detection_settings_requested.emit(self.settings())
    def _detect(self):self.detect_requested.emit(self.settings())
    def _exclude(self,item):
        spoke=next(s for s in self.session.spokes if s.id==item.data(Qt.UserRole));self.spoke_requested.emit(replace(spoke,excluded=item.checkState()!=Qt.Checked))
    def set_axes(self,axes):
        self.axis.blockSignals(True);self.axis.clear()
        for a in axes:self.axis.addItem(a['name'],a['id'])
        if self.axis.findData(self.session.axis)<0:self.axis.addItem(getattr(self.session,'axis_definition',{}).get('name',AXES.get(self.session.axis,self.session.axis)),self.session.axis)
        self.axis.setCurrentIndex(self.axis.findData(self.session.axis));self.axis.blockSignals(False)
    def set_devices(self,names):
        self.device.blockSignals(True);self.device.clear();self.device.addItem('', '')
        for name in names:self.device.addItem(name,name)
        self.device.setCurrentText(self.session.device);self.device.blockSignals(False)
    def refresh(self):
        s=self.session
        self.stage_boxes['calibration'].setEnabled(s.image is not None)
        self.stage_boxes['spokes'].setEnabled(s.image is not None)
        fields=(self.device,self.axis,self.spoke_list,self.radius,self.peak_height,self.calibration_method,self.known_length,self.pixel_length,self.center_method)
        for widget in fields:widget.blockSignals(True)
        self.device.setCurrentText(s.device)
        self.axis.setCurrentIndex(self.axis.findData(s.axis));self.calibration_method.setCurrentIndex(self.calibration_method.findData('numeric' if s.calibration_mode=='manual' else s.calibration_mode))
        c=s.calibration
        self.calibration_label.setText(s.calibration_error or (f'{c.source}: X {c.sx_mm:.6g}, Y {c.sy_mm:.6g} mm/px' if c else '未校正：pxで評価します'))
        self.numeric_frame.setVisible(True)
        self.numeric_frame.setEnabled(s.calibration_mode in ('numeric','manual'))
        if c and c.reference:self.known_length.setValue(c.reference[2])
        if c and not self.pixel_length.hasFocus():self.pixel_length.setText(f'{c.sx_mm:.12g}')
        if c and s.calibration_mode in ('numeric','manual') and c.sx_mm!=c.sy_mm:
            self.calibration_label.setText(self.calibration_label.text()+'\n入力値の変更後はX・Yに同じ値を使用します。')
        if s.detection_settings:self.radius.setValue(s.detection_settings.radius_ratio*100);self.peak_height.setValue(s.detection_settings.min_peak_height*100)
        selected=self.spoke_list.currentItem().data(Qt.UserRole) if self.spoke_list.currentItem() else None
        self.spoke_list.setVisible(True)
        self.stage_boxes['result'].setVisible(bool(s.spokes) or s.result is not None)
        self.spoke_list.clear()
        for i,spoke in enumerate(s.spokes):
            item=QListWidgetItem(f'帯 {i+1}');item.setData(Qt.UserRole,spoke.id);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Unchecked if spoke.excluded else Qt.Checked);self.spoke_list.addItem(item)
            if spoke.id==selected:self.spoke_list.setCurrentItem(item)
        self.center_method.setCurrentIndex(self.center_method.findData(s.center_method))
        for widget in fields:widget.blockSignals(False)
        self.laser_button.setEnabled(s.image is not None)
        self.laser_step.setText('指定済み' if s.laser else '未指定（基準点選択ボタンで指定）')
        self.warnings.setText('' if s.image and s.laser is None and not s.calibration_error else s.readiness_message)
        self.detect_button.setEnabled(s.can_detect);self.save_button.setEnabled(s.ready_for_review and s.dirty)
        self.detail_button.setEnabled(s.result is not None and s.result.selected is not None and not s.requires_redetection)
        calibration=f'X {c.sx_mm:.6g}, Y {c.sy_mm:.6g} mm/px ({c.source})' if c else '未校正（px）'
        laser=f'({s.laser.x:.3f}, {s.laser.y:.3f}) px' if s.laser else '未指定'
        self.summary.setText(result_table([
            ('画像名',s.image.path.name if s.image else '画像未選択'),
            ('装置名',s.device or '未入力'),('回転軸',self.axis.currentText()),
            ('解像度',calibration),('レーザー基準点',laser)]))
        centroid=s.center_method=='intersection_centroid'
        m=s.result.selected if s.result else None
        if m:
            center=m.center if centroid else m.circle.center
            rows=[('解析方式',METHODS[s.center_method]),
                  ('使用帯数',f'{len(s.result.active_spoke_ids)}本'),
                  ('中心偏位（レーザー中心基準）',f'{m.laser_distance:.4f} {m.unit}'),
                  ('偏位X',f'{m.laser_delta.x:+.4f} {m.unit}'),('偏位Y',f'{m.laser_delta.y:+.4f} {m.unit}'),
                  ('最大距離' if centroid else '最大半径',f'{m.max_distance if centroid else m.circle.radius:.4f} {m.unit}'),
                  ('推定中心',f'X {center.x:.4f} / Y {center.y:.4f} {m.unit}')]
            if centroid:
                numbers={spoke.id:str(i+1) for i,spoke in enumerate(s.spokes)}
                skipped='、'.join('–'.join(numbers.get(key,key) for key in pair) for pair in m.skipped_pairs) or 'なし'
                rows.extend([('使用交点',f'{len(m.intersections)}個'),('計算不能ペア',f'{len(m.skipped_pairs)}組（{skipped}）')])
                warning='\n'.join(m.warnings)
                for key,number in numbers.items():warning=warning.replace(key,number)
                if warning:rows.append(('警告',warning))
            text=result_table(rows)
            text+='<p>偏位：Xは右、Yは上が正。<br>中心座標：Xは右、Yは下向き。<br>画像：水色＝レーザー、赤＝重心、紫＝最小円中心、白＝交点</p>'
            if s.readiness_message:text+='<p>'+escape(s.readiness_message)+'</p>'
            self.result_label.setText(text)
        else:
            reason=(s.result.centroid_error if centroid and s.result else s.error) or '照射帯の検出後に結果を表示します'
            self.result_label.setText(escape(reason))
        self.result_label.setEnabled(s.ready_for_review)
