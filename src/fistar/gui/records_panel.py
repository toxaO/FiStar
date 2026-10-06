from datetime import datetime,timedelta
from PySide6.QtCore import Qt,QDate,Signal,QPointF
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QCheckBox,QDateEdit,QPushButton,QTableWidget,QTableWidgetItem,QLabel,QFileDialog,QMessageBox,QHeaderView)
from fistar.storage.repository import list_measurements,list_devices,delete_measurement
from .analysis_panel import AXES,STATUS,METHODS

class TrendPlot(QWidget):
    def __init__(self):
        super().__init__(); self.records=(); self.unit='mm'; self.metric_name='radius'; self.center_method='minimax'; self.enabled=False; self.setMinimumHeight(220)
    def points(self):
        points=[]
        for record in reversed(self.records):
            if record.result.center_method!=self.center_method: continue
            centroid=self.center_method=='intersection_centroid'
            m=(record.result.centroid_physical if self.unit=='mm' else record.result.centroid_pixels) if centroid else (record.result.physical if self.unit=='mm' else record.result.pixels)
            if m is not None:
                value=(m.max_distance if centroid else m.circle.radius) if self.metric_name=='radius' else m.laser_distance
                points.append((datetime.fromisoformat(record.created_at).timestamp(),value))
        return points
    def paintEvent(self,event):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#f2f6f8')); p.setPen(QColor('#223846'))
        p.drawText(14,22,(('交点までの最大距離' if self.center_method=='intersection_centroid' else '半径') if self.metric_name=='radius' else 'レーザー偏位')+f' ({self.unit})')
        if not self.enabled: p.drawText(14,55,'装置と軸を選択するとトレンドを表示します'); return
        points=self.points()
        if not points: p.drawText(14,55,'該当する単位の記録はありません'); return
        times=[a for a,b in points]; values=[b for a,b in points]
        start,end=min(times),max(times); maximum=max(max(values)*1.15,.001)
        left,right,top,bottom=65,self.width()-20,42,self.height()-35
        p.setPen(QPen(QColor('#a5b5c0'),1)); p.drawLine(left,top,left,bottom); p.drawLine(left,bottom,right,bottom)
        p.drawText(6,top+5,f'{maximum:.3g}'); p.drawText(35,bottom,'0')
        p.drawText(left,bottom+22,datetime.fromtimestamp(start).strftime('%Y/%m/%d'))
        p.drawText(max(left,right-90),bottom+22,datetime.fromtimestamp(end).strftime('%Y/%m/%d'))
        scaled=[QPointF((left+right)/2 if end==start else left+(t-start)/(end-start)*(right-left),bottom-v/maximum*(bottom-top)) for t,v in points]
        p.setPen(QPen(QColor('#087e8b'),2))
        for a,b in zip(scaled,scaled[1:]): p.drawLine(a,b)
        p.setBrush(QColor('#087e8b'))
        for point in scaled: p.drawEllipse(point,3,3)

class RecordsPanel(QWidget):
    reopen_requested=Signal(object)
    def __init__(self,connection):
        super().__init__(); self.connection=connection; self.records=()
        root=QVBoxLayout(self); filters=QHBoxLayout()
        self.device=QComboBox(); self.axis=QComboBox(); self.axis.addItem('全ての軸',None)
        for key,label in AXES.items(): self.axis.addItem(label,key)
        filters.addWidget(QLabel('装置')); filters.addWidget(self.device); filters.addWidget(self.axis)
        self.date_filter=QCheckBox('日付で絞る'); filters.addWidget(self.date_filter)
        self.since=QDateEdit(QDate.currentDate().addMonths(-12)); self.until=QDateEdit(QDate.currentDate())
        for w in (self.since,self.until): w.setCalendarPopup(True); filters.addWidget(w)
        root.addLayout(filters)
        for combo in (self.device,self.axis): combo.currentIndexChanged.connect(self.refresh)
        self.date_filter.toggled.connect(self.refresh); self.since.dateChanged.connect(self.refresh); self.until.dateChanged.connect(self.refresh)
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(['日時','画像名','装置','軸','有効帯数','広がり指標','レーザー偏位','方式'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True); self.table.itemSelectionChanged.connect(self.show_detail); root.addWidget(self.table)
        self.detail=QLabel('記録を選択してください'); self.detail.setWordWrap(True); root.addWidget(self.detail)
        tools=QHBoxLayout()
        for label,action in [('一覧をCSV出力',self.export_csv),('選択記録をPDF出力',self.export_pdf),('選択記録を再度開く',self.reopen),('選択記録を削除',self.delete)]:
            b=QPushButton(label); b.clicked.connect(action); tools.addWidget(b)
        root.addLayout(tools)
        options=QHBoxLayout(); self.metric=QComboBox(); self.metric.addItem('半径','radius'); self.metric.addItem('レーザー偏位','laser_distance')
        self.method=QComboBox()
        for value,label in METHODS.items(): self.method.addItem(label,value)
        options.addWidget(self.method)
        self.unit=QComboBox(); self.unit.addItems(['mm','px']); options.addWidget(QLabel('トレンド')); options.addWidget(self.metric); options.addWidget(self.unit); options.addStretch(); root.addLayout(options)
        self.trend=TrendPlot(); root.addWidget(self.trend)
        self.method.currentIndexChanged.connect(self.update_trend)
        self.metric.currentIndexChanged.connect(self.update_trend); self.unit.currentIndexChanged.connect(self.update_trend)
        self.refresh()
    def refresh(self,*args):
        selected=self.device.currentData(); self.device.blockSignals(True); self.device.clear(); self.device.addItem('全ての装置',None)
        for device in list_devices(self.connection): self.device.addItem(device,device)
        index=self.device.findData(selected); self.device.setCurrentIndex(max(0,index)); self.device.blockSignals(False)
        since=until=None
        if self.date_filter.isChecked():
            since=datetime.combine(self.since.date().toPython(),datetime.min.time()).astimezone().isoformat()
            until=datetime.combine(self.until.date().toPython()+timedelta(days=1),datetime.min.time()).astimezone().isoformat()
        self.records=list_measurements(self.connection,self.device.currentData(),self.axis.currentData(),since,until)
        self.table.setRowCount(len(self.records))
        for row,record in enumerate(self.records):
            m=record.result.selected; centroid=record.result.center_method=='intersection_centroid'
            spread=m.max_distance if centroid else m.circle.radius
            values=[datetime.fromisoformat(record.created_at).astimezone().strftime('%Y/%m/%d %H:%M'),record.image_name,record.device,AXES[record.axis],str(len(record.result.active_spoke_ids)),('最大交点距離 ' if centroid else '半径 ')+f'{spread:.4f} {m.unit}',f'{m.laser_distance:.4f} {m.unit}',METHODS[record.result.center_method]]
            for col,value in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(value))
        self.show_detail(); self.update_trend()
    def selected(self):
        row=self.table.currentRow()
        return self.records[row] if 0<=row<len(self.records) else None
    def show_detail(self):
        r=self.selected()
        if not r: self.detail.setText('記録を選択してください'); return
        m=r.result.selected; c=r.snapshot.get('calibration')
        if r.result.center_method=='intersection_centroid':
            self.detail.setText(f'交点重心方式：合否判定なし\n交点 {len(m.intersections)}個 ／ 計算不能ペア {len(m.skipped_pairs)}組\n実画像の臨床的精度は未検証'); return
        self.detail.setText(f'保存時の評価：半径 {STATUS[r.judgment.radius]} ／ 偏位 {STATUS[r.judgment.laser_distance]}\n許容値：半径 {r.limits.radius if r.limits.radius is not None else "未設定"}、偏位 {r.limits.laser_distance if r.limits.laser_distance is not None else "未設定"} ({r.limits.unit})\n校正：{c["source"] if c else "未校正"} ／ 有効帯 {len(r.result.active_spoke_ids)}本 ／ チャンネル {r.snapshot.get("channel","—")}\n実画像の臨床的精度は未検証')
    def update_trend(self):
        self.trend.center_method=self.method.currentData()
        self.metric.setItemText(0,'交点までの最大距離' if self.trend.center_method=='intersection_centroid' else '半径')
        self.trend.records=self.records; self.trend.unit=self.unit.currentText(); self.trend.metric_name=self.metric.currentData()
        self.trend.enabled=self.device.currentData() is not None and self.axis.currentData() is not None; self.trend.update()
    def delete(self):
        r=self.selected()
        if r and QMessageBox.question(self,'記録の削除',f'{r.image_name} の記録を削除しますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            try: delete_measurement(self.connection,r.id); self.refresh()
            except Exception as e: QMessageBox.warning(self,'削除できません',str(e))
    def reopen(self):
        r=self.selected()
        if r: self.reopen_requested.emit(r)
    def export_csv(self):
        path,_=QFileDialog.getSaveFileName(self,'一覧をCSV保存','fistar.csv','CSV (*.csv)')
        if path:
            try:
                from fistar.exporting import export_csv
                export_csv(self.records,path)
            except Exception as e: QMessageBox.warning(self,'出力できません',str(e))
    def export_pdf(self):
        r=self.selected()
        if not r: return
        path,_=QFileDialog.getSaveFileName(self,'要約PDFを保存','fistar.pdf','PDF (*.pdf)')
        if path:
            try:
                from fistar.exporting import export_pdf
                export_pdf(r,path)
            except Exception as e: QMessageBox.warning(self,'出力できません',str(e))
