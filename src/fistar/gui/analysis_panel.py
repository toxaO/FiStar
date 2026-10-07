from dataclasses import replace
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QLabel,QPushButton,QComboBox,QLineEdit,QFormLayout,QDoubleSpinBox,QListWidget,QListWidgetItem,QTableWidget,QTableWidgetItem,QHeaderView)
from fistar.core.models import DetectionSettings

AXES={'gantry':'ガントリ','collimator':'コリメータ','couch':'カウチ'}
METHODS={'minimax':'最小円方式','intersection_centroid':'交点重心方式'}
STATUS={'not_evaluated':'判定なし','within':'許容内','exceeded':'許容超過','unset':'未設定','unit_mismatch':'単位不一致（判定なし）'}

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
    limits_requested=Signal()
    def __init__(self,session):
        super().__init__();self.setObjectName('analysisPanel');self.setAttribute(Qt.WA_StyledBackground,True); self.session=session;self.confirm_buttons={};self.stage_boxes={}
        root=QVBoxLayout(self);root.setContentsMargins(4,0,4,4);root.setSpacing(12)
        def group(title,key):
            box=QGroupBox(title);layout=QVBoxLayout(box);layout.setContentsMargins(5,4,5,4);layout.setSpacing(5);root.addWidget(box);self.stage_boxes[key]=box;return layout
        layout=group('1  装置と回転軸','identity')
        self.device=QLineEdit();self.device.setPlaceholderText('装置名（空欄はtemp）')
        self.axis=QComboBox()
        for value,label in AXES.items():self.axis.addItem(label,value)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);form.addRow('装置名（任意）',self.device);form.addRow('回転軸',self.axis);layout.addLayout(form)
        self.device.editingFinished.connect(self._identity);self.axis.currentIndexChanged.connect(self._identity)
        layout=group('距離校正','calibration')
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
        self.laser_step=QLabel('未指定（画像で指定）');self.laser_step.setWordWrap(True);laser_layout.addWidget(self.laser_step)
        layout=group('3  照射帯の検出','spokes')
        detection_row=QHBoxLayout();detection_row.setSpacing(8);detection_left=QWidget();left_layout=QVBoxLayout(detection_left);left_layout.setContentsMargins(0,0,0,0);left_layout.setSpacing(8)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.WrapLongRows);self.radius=QDoubleSpinBox();self.peak_height=QDoubleSpinBox()
        self.radius.setRange(5,95);self.radius.setDecimals(1);self.radius.setSuffix(' %');self.radius.setValue(85)
        self.peak_height.setRange(.1,99.9);self.peak_height.setDecimals(1);self.peak_height.setSuffix(' %');self.peak_height.setValue(25)
        radius_tip='レーザー点から最も近い画像端までの距離に対する割合です。85%ならその距離の0.85倍の探索円を使います。変更すると画像に円を表示します。'
        peak_tip='円周プロファイルの最大ピークに対する検出下限です。25%なら最大ピークの1/4以上が候補です。低くすると弱い帯とノイズを拾いやすくなります。半値幅の50%とは別の設定です。'
        for label,field,tip in [('探索円の半径',self.radius,radius_tip),('最小ピーク高さ',self.peak_height,peak_tip)]:
            text=QLabel(label);text.setToolTip(tip);field.setToolTip(tip);form.addRow(text,field)
        left_layout.addLayout(form)
        self.radius.valueChanged.connect(self._settings_changed);self.peak_height.valueChanged.connect(self._settings_changed)
        self.detect_button=QPushButton('照射帯を検出');self.detect_button.setProperty('primary',True);self.detect_button.clicked.connect(self._detect);left_layout.addWidget(self.detect_button)
        self.warnings=QLabel();self.warnings.setWordWrap(True);left_layout.addWidget(self.warnings)
        self.spoke_list=QListWidget();self.spoke_list.setMinimumWidth(85);self.spoke_list.setMaximumWidth(115);self.spoke_list.setMinimumHeight(145);self.spoke_list.setMaximumHeight(220);self.spoke_list.itemChanged.connect(self._exclude)
        self.spoke_list.currentItemChanged.connect(lambda item,old:self.selected_requested.emit(item.data(Qt.UserRole)) if item else None);detection_row.addWidget(detection_left,1);detection_row.addWidget(self.spoke_list);layout.addLayout(detection_row)
        layout=group('4  結果の確認','result')
        self.center_method=QComboBox()
        for value,label in METHODS.items():self.center_method.addItem(label,value)
        self.center_method.currentIndexChanged.connect(lambda:self.center_method_requested.emit(self.center_method.currentData()));layout.addWidget(self.center_method)
        self.detail_button=QPushButton('中心付近を拡大');self.detail_button.clicked.connect(self.detail_requested.emit);layout.addWidget(self.detail_button)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.result_label=QLabel();self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
        note=QLabel('校正・レーザー位置・検出帯と結果を画像で確認してから保存してください。実画像の臨床的精度は未検証です。');note.setWordWrap(True);layout.addWidget(note)
        self.save_button=QPushButton('結果を確認して保存');self.save_button.setProperty('primary',True);self.save_button.clicked.connect(self.save_requested.emit);root.addWidget(self.save_button);root.addStretch()
    def _identity(self):self.identity_requested.emit(self.device.text(),self.axis.currentData())
    def settings(self):return DetectionSettings(self.radius.value()/100,self.peak_height.value()/100,'dark')
    def _settings_changed(self):self.detection_settings_requested.emit(self.settings())
    def _detect(self):self.detect_requested.emit(self.settings())
    def _exclude(self,item):
        spoke=next(s for s in self.session.spokes if s.id==item.data(Qt.UserRole));self.spoke_requested.emit(replace(spoke,excluded=item.checkState()!=Qt.Checked))
    def refresh(self,limits=None):
        s=self.session
        self.stage_boxes['calibration'].setEnabled(s.image is not None)
        self.stage_boxes['spokes'].setEnabled(s.image is not None)
        fields=(self.device,self.axis,self.spoke_list,self.radius,self.peak_height,self.calibration_method,self.known_length,self.pixel_length,self.center_method)
        for widget in fields:widget.blockSignals(True)
        if not self.device.hasFocus():self.device.setText(s.device)
        self.axis.setCurrentIndex(self.axis.findData(s.axis));self.calibration_method.setCurrentIndex(self.calibration_method.findData('numeric' if s.calibration_mode=='manual' else s.calibration_mode))
        c=s.calibration
        self.calibration_label.setText(s.calibration_error or (f'{c.source}: X {c.sx_mm:.6g}, Y {c.sy_mm:.6g} mm/px' if c else '未校正：pxで評価します'))
        self.numeric_frame.setVisible(s.calibration_mode in ('numeric','manual'))
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
        self.laser_step.setText('指定済み' if s.laser else '未指定（画像で指定）')
        self.warnings.setText('' if s.image and s.laser is None and not s.calibration_error else s.readiness_message)
        self.detect_button.setEnabled(s.can_detect);self.save_button.setEnabled(s.ready_for_review and s.dirty)
        self.detail_button.setEnabled(s.result is not None and s.result.selected is not None and not s.requires_redetection)
        calibration=f'X {c.sx_mm:.6g}, Y {c.sy_mm:.6g} mm/px ({c.source})' if c else '未校正（px）'
        laser=f'({s.laser.x:.3f}, {s.laser.y:.3f}) px' if s.laser else '未指定'
        self.summary.setText(f'{s.image.path.name if s.image else "画像未選択"}\n装置：{s.device} ／ {AXES[s.axis]}\n校正：{calibration}\nレーザー：{laser}\n'+(s.readiness_message or '保存前に画像と結果を確認してください'))
        centroid=s.center_method=='intersection_centroid'
        if centroid:
            m=s.result.selected if s.result else None
            if m:
                numbers={spoke.id:str(i+1) for i,spoke in enumerate(s.spokes)}
                skipped='、'.join('–'.join(numbers[id] for id in pair) for pair in m.skipped_pairs) or 'なし'
                warning_text='\n'.join(m.warnings)
                for id,number in numbers.items(): warning_text=warning_text.replace('帯ID '+id,'帯 '+number).replace(' / '+id+'：',' / '+number+'：')
                self.result_label.setText(f'交点重心方式：合否判定なし\n中心：({m.center.x:.4f}, {m.center.y:.4f}) {m.unit}\nレーザー偏位：{m.laser_distance:.4f} {m.unit}\n成分：X {m.laser_delta.x:+.4f}, Y {m.laser_delta.y:+.4f} {m.unit}\n使用交点：{len(m.intersections)}個\n計算不能ペア：{len(m.skipped_pairs)}組（{skipped}）\n交点までの最大距離：{m.max_distance:.4f} {m.unit}\nXは右、Yは下が正\n画像：水色＝レーザー、赤＝重心、白＝交点\n'+warning_text)
            else: self.result_label.setText((s.result.centroid_error if s.result else s.error) or '中心線の確認後に計算します')
        elif s.result:
            m=s.result.primary
            from fistar.core.analysis import judge
            from fistar.core.models import Limits
            j=judge(m,limits or Limits())
            limit=lambda value: '未設定' if value is None else f'{value:.6g} {(limits.unit if limits else "mm")}'
            self.result_label.setText(f'解析日時：{s.analysis_at}\n{s.image.path.name} ／ {s.device} ／ {AXES[s.axis]}\n有効な帯：{len(s.result.active_spoke_ids)}本\n半径：{m.circle.radius:.4f} {m.unit}（{STATUS[j.radius]}）\n半径の上限：{limit(limits.radius if limits else None)}\nレーザー偏位：{m.laser_distance:.4f} {m.unit}（{STATUS[j.laser_distance]}）\n偏位の上限：{limit(limits.laser_distance if limits else None)}\n成分：X {m.laser_delta.x:+.4f}, Y {m.laser_delta.y:+.4f} {m.unit}\n中心：({m.circle.center.x:.4f}, {m.circle.center.y:.4f}) {m.unit}\nXは右、Yは下が正')
        else: self.result_label.setText(s.error or '照射帯の検出後に結果を表示します')
        self.result_label.setEnabled(s.ready_for_review)
