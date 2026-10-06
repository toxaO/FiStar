from dataclasses import replace
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QLabel,QPushButton,QComboBox,QLineEdit,QFormLayout,QDoubleSpinBox,QListWidget,QListWidgetItem,QTableWidget,QTableWidgetItem,QHeaderView)
from fistar.core.models import DetectionSettings

AXES={'gantry':'ガントリ','collimator':'コリメータ','couch':'カウチ'}
METHODS={'minimax':'最小円方式','intersection_centroid':'交点重心方式'}
STATUS={'not_evaluated':'判定なし','within':'許容内','exceeded':'許容超過','unset':'未設定','unit_mismatch':'単位不一致（判定なし）'}

class AnalysisPanel(QWidget):
    open_requested=Signal()
    identity_requested=Signal(str,str)
    calibration_requested=Signal(str)
    mode_requested=Signal(str)
    detect_requested=Signal(object)
    spoke_requested=Signal(object)
    selected_requested=Signal(str)
    confirm_requested=Signal(str)
    center_method_requested=Signal(str)
    detail_requested=Signal()
    save_requested=Signal()
    limits_requested=Signal()
    def __init__(self,session):
        super().__init__(); self.session=session
        root=QVBoxLayout(self); root.setSpacing(10)
        self.confirm_buttons={}
        self.stage_boxes={}
        def group(title,step):
            box=QGroupBox(title); layout=QVBoxLayout(box); root.addWidget(box)
            self.stage_boxes[step]=box
            button=QPushButton('この段階を確認'); button.clicked.connect(lambda checked=False,k=step:self.confirm_requested.emit(k))
            self.confirm_buttons[step]=button
            return layout,button
        layout,confirm=group('1  画像','image')
        load=QPushButton('TIFFを開く'); load.clicked.connect(self.open_requested.emit); layout.addWidget(load)
        self.image_label=QLabel('画像未選択'); self.image_label.setWordWrap(True); layout.addWidget(self.image_label)
        layout.addWidget(QLabel('解析チャンネル：輝度（固定）')); layout.addWidget(confirm)
        layout,confirm=group('2  装置と回転軸','identity')
        self.device=QLineEdit(); self.device.setPlaceholderText('装置名')
        self.registered_device=QComboBox(); self.registered_device.addItem('登録済み装置から選択',None)
        self.registered_device.currentIndexChanged.connect(self._select_device)
        self.axis=QComboBox()
        for value,label in AXES.items(): self.axis.addItem(label,value)
        self.device.editingFinished.connect(self._identity)
        self.axis.currentIndexChanged.connect(self._identity)
        layout.addWidget(self.device); layout.addWidget(self.registered_device); layout.addWidget(self.axis); layout.addWidget(confirm)
        limits=QPushButton('装置・軸の許容値を設定'); limits.clicked.connect(self.limits_requested.emit); layout.addWidget(limits)
        layout,confirm=group('3  距離校正','calibration')
        self.calibration_label=QLabel(); self.calibration_label.setWordWrap(True); layout.addWidget(self.calibration_label)
        self.known_length=QDoubleSpinBox(); self.known_length.setRange(.001,10000); self.known_length.setDecimals(3); self.known_length.setValue(10); self.known_length.setSuffix(' mm（既知長さ）'); layout.addWidget(self.known_length)
        for label,action in [('画像上で2点を指定','manual'),('TIFFタグを使用','tag'),('未校正（px）で進む','none')]:
            b=QPushButton(label); b.clicked.connect(lambda checked=False,a=action:self.calibration_requested.emit(a)); layout.addWidget(b)
        layout.addWidget(confirm)
        layout,confirm=group('4  レーザー基準点','laser')
        b=QPushButton('画像上でレーザー点を指定（右クリック）'); b.clicked.connect(lambda:self.mode_requested.emit('laser')); layout.addWidget(b)
        self.laser_label=QLabel('未指定'); layout.addWidget(self.laser_label); layout.addWidget(confirm)
        layout,confirm=group('5  照射帯の検出と修正','spokes')
        form=QFormLayout(); self.radius=QDoubleSpinBox(); self.peak_height=QDoubleSpinBox()
        self.radius.setRange(5,95); self.radius.setDecimals(1); self.radius.setSuffix(' %')
        self.peak_height.setRange(.1,99.9); self.peak_height.setDecimals(1); self.peak_height.setSuffix(' %')
        form.addRow('探索円の半径',self.radius); form.addRow('最小ピーク高さ',self.peak_height)
        self.peak_height.setToolTip('円周プロファイルの最大ピークに対する検出下限です。25%なら最大ピークの1/4以上の高さを候補にします。低くすると弱い帯を拾いやすく、高くするとノイズを除きやすくなります。半値幅の50%とは別の設定です。')
        self.polarity=QComboBox(); self.polarity.addItem('暗い帯','dark'); self.polarity.addItem('明るい帯','bright'); form.addRow('極性',self.polarity)
        layout.addLayout(form)
        self.detect_button=QPushButton('照射帯を自動検出'); self.detect_button.clicked.connect(self._detect); layout.addWidget(self.detect_button)
        self.warnings=QLabel(); self.warnings.setWordWrap(True); layout.addWidget(self.warnings)
        self.spoke_list=QListWidget(); self.spoke_list.setMaximumHeight(160)
        self.spoke_list.itemChanged.connect(self._exclude)
        self.spoke_list.currentItemChanged.connect(lambda item,old:self.selected_requested.emit(item.data(Qt.UserRole)) if item else None)
        layout.addWidget(self.spoke_list)
        tip=QLabel('本数・中心線を確認してください。チェックを外すと帯を除外します。反対向きの腕は1本の帯です。'); tip.setWordWrap(True); layout.addWidget(tip)
        layout.addWidget(confirm)
        layout,confirm=group('6  結果確認','result')
        self.center_method=QComboBox()
        for value,label in METHODS.items(): self.center_method.addItem(label,value)
        self.center_method.currentIndexChanged.connect(lambda:self.center_method_requested.emit(self.center_method.currentData()))
        layout.addWidget(self.center_method)
        self.detail_button=QPushButton('中心付近を拡大'); self.detail_button.clicked.connect(self.detail_requested.emit); layout.addWidget(self.detail_button)
        self.intersection_table=QTableWidget(0,4); self.intersection_table.setHorizontalHeaderLabels(['帯ペア','交点X','交点Y','重心からの距離'])
        self.intersection_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.intersection_table.setEditTriggers(QTableWidget.NoEditTriggers); self.intersection_table.setMaximumHeight(210)
        layout.addWidget(self.intersection_table)
        self.result_label=QLabel(); self.result_label.setWordWrap(True); layout.addWidget(self.result_label)
        note=QLabel('実画像の臨床的精度は未検証です。施設手順により操作者が最終判断してください。'); note.setWordWrap(True); layout.addWidget(note)
        layout.addWidget(confirm)
        self.save_button=QPushButton('確認済み結果を保存'); self.save_button.clicked.connect(self.save_requested.emit); root.addWidget(self.save_button); root.addStretch()
    def _identity(self): self.identity_requested.emit(self.device.text(),self.axis.currentData())
    def _select_device(self):
        name=self.registered_device.currentData()
        if name is not None: self.device.setText(name); self._identity()
    def set_devices(self,devices):
        self.registered_device.blockSignals(True); self.registered_device.clear()
        self.registered_device.addItem('登録済み装置から選択',None)
        for name in devices: self.registered_device.addItem(name,name)
        self.registered_device.blockSignals(False)
    def _detect(self):
        try:
            self.detect_requested.emit(DetectionSettings(self.radius.value()/100,self.peak_height.value()/100,self.polarity.currentData()))
        except ValueError as error: self.warnings.setText(str(error))
    def _exclude(self,item):
        spoke=next(s for s in self.session.spokes if s.id==item.data(Qt.UserRole))
        self.spoke_requested.emit(replace(spoke,excluded=item.checkState()!=Qt.Checked))
    def refresh(self,limits=None):
        s=self.session
        if s.image:
            raw=s.image.raw; h,w=raw.shape[:2]
            self.image_label.setText(f'{s.image.path.name}\n{w} × {h} px ／ {raw.dtype.itemsize*8} bit ／ '+('RGB' if raw.ndim==3 else 'グレースケール')+'\n解像度タグ：'+('利用可能' if s.image.tagged_calibration else 'なし／校正不能'))
        else: self.image_label.setText('画像未選択')
        for widget in (self.device,self.axis,self.spoke_list): widget.blockSignals(True)
        self.device.setText(s.device); self.axis.setCurrentIndex(self.axis.findData(s.axis))
        c=s.calibration
        self.calibration_label.setText(f'{c.source}: X {c.sx_mm:.6g}, Y {c.sy_mm:.6g} mm/px' if c else '未校正：pxで評価します')
        self.laser_label.setText(f'x={s.laser.x:.2f}, y={s.laser.y:.2f} px' if s.laser else '未指定')
        if s.detection_settings:
            self.radius.setValue(s.detection_settings.radius_ratio*100)
            self.peak_height.setValue(s.detection_settings.min_peak_height*100)
            self.polarity.setCurrentIndex(self.polarity.findData(s.detection_settings.polarity))
        self.known_length.setValue(c.reference[2] if c and c.reference else 10)
        selected=self.spoke_list.currentItem().data(Qt.UserRole) if self.spoke_list.currentItem() else None
        self.spoke_list.clear()
        for i,spoke in enumerate(s.spokes):
            item=QListWidgetItem(f'帯 {i+1}  '+('旧修正線' if spoke.origin=='manual' else '自動'))
            item.setData(Qt.UserRole,spoke.id); item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if spoke.excluded else Qt.Checked); self.spoke_list.addItem(item)
            if spoke.id==selected: self.spoke_list.setCurrentItem(item)
        for widget in (self.device,self.axis,self.spoke_list): widget.blockSignals(False)
        info=''
        if s.detection:
            info=('旧方式の記録です。再検出するとPylinac方式に切り替わります。' if s.detection.method=='legacy-threshold-tls' else f'Pylinac {s.detection.pylinac_version} ／ 検出点 {len(s.detection.points)}個')
            info+='／'.join(s.detection.warnings)
        if s.channel!='luminance': info+='\n旧記録の解析チャンネル：'+s.channel+'。表示は輝度固定です。輝度で再検出してから保存してください。'
        self.warnings.setText(info)
        self.detect_button.setEnabled(s.laser is not None and all(k in s.confirmed_steps for k in s.steps[:4]))
        for i,step in enumerate(s.steps):
            button=self.confirm_buttons[step]
            button.setText('確認済み ✓' if step in s.confirmed_steps else 'この段階を確認')
            button.setEnabled(all(k in s.confirmed_steps for k in s.steps[:i]))
            self.stage_boxes[step].setEnabled(all(k in s.confirmed_steps for k in s.steps[:i]))
        self.save_button.setEnabled(s.can_save and s.dirty)
        self.center_method.blockSignals(True); self.center_method.setCurrentIndex(self.center_method.findData(s.center_method)); self.center_method.blockSignals(False)
        self.detail_button.setEnabled(s.result is not None and s.result.selected is not None)
        centroid=s.center_method=='intersection_centroid'
        self.intersection_table.setVisible(centroid); self.intersection_table.setRowCount(0)
        if centroid:
            m=s.result.selected if s.result else None
            if m:
                numbers={spoke.id:str(i+1) for i,spoke in enumerate(s.spokes)}
                self.intersection_table.setRowCount(len(m.intersections))
                for row,p in enumerate(m.intersections):
                    values=['–'.join(numbers[id] for id in p.spoke_ids),f'{p.point.x:.4f}',f'{p.point.y:.4f}',f'{p.distance:.4f} {m.unit}']
                    for col,value in enumerate(values): self.intersection_table.setItem(row,col,QTableWidgetItem(value))
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
        else: self.result_label.setText(s.error or '中心線の確認後に計算します')
