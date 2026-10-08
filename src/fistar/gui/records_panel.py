from datetime import datetime,timedelta
from PySide6.QtCore import Qt,QDate,Signal,QPointF
from PySide6.QtGui import QPainter,QColor,QPen,QFont
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QCheckBox,QDateEdit,QPushButton,QTableWidget,QTableWidgetItem,QLabel,QFileDialog,QMessageBox,QHeaderView,QInputDialog,QDialog)
from fistar.storage.repository import list_measurements,list_record_devices,delete_measurement
from .analysis_panel import AXES,METHODS

class TrendPlot(QWidget):
    def __init__(self):
        super().__init__(); self.records=(); self.unit='mm'; self.metric_name='laser_distance'; self.center_method='intersection_centroid'; self.enabled=False;self.highlight_id=None; self.setMinimumHeight(220)
    def plotted_records(self):
        centroid=self.center_method=='intersection_centroid'
        def available(record):
            result=record.result
            metric=(result.centroid_physical if self.unit=='mm' else result.centroid_pixels) if centroid else (result.physical if self.unit=='mm' else result.pixels)
            return result.center_method==self.center_method and metric is not None
        return sorted((r for r in self.records if available(r)),key=lambda r:(datetime.fromisoformat(r.created_at).timestamp(),r.id))
    def points(self,component='distance'):
        points=[]
        for record in self.plotted_records():
            if record.result.center_method!=self.center_method: continue
            centroid=self.center_method=='intersection_centroid'
            m=(record.result.centroid_physical if self.unit=='mm' else record.result.centroid_pixels) if centroid else (record.result.physical if self.unit=='mm' else record.result.pixels)
            if m is not None:
                value=(m.max_distance if centroid else m.circle.radius) if self.metric_name=='radius' else {'distance':m.laser_distance,'x':m.laser_delta.x,'y':m.laser_delta.y}[component]
                points.append((datetime.fromisoformat(record.created_at).timestamp(),value))
        return points
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing,True)
        p.fillRect(self.rect(),QColor('#f2f6f8'));p.setPen(QColor('#223846'))
        radius=self.metric_name=='radius'
        spread_label='最大距離' if self.center_method=='intersection_centroid' else '最大半径'
        title=spread_label if radius else '中心偏位（レーザー中心基準）'
        if radius and self.center_method=='intersection_centroid':title+='（重心から交点までの最大距離）'
        p.drawText(14,22,title+f' ({self.unit})')
        if not self.enabled:p.drawText(14,55,'装置と軸を選択するとトレンドを表示します');return
        definitions=[('distance',spread_label,'#087e8b')] if radius else [('distance','直線距離','#087e8b'),('x','X成分（右が正）','#ce6535'),('y','Y成分（上が正）','#7356b5')]
        series=[(label,color,self.points(key)) for key,label,color in definitions]
        points=[point for _,_,items in series for point in items]
        if not points:p.drawText(14,55,'対象記録なし');return
        x=14
        for label,color,_ in series:
            p.setPen(QPen(QColor(color),2));p.drawLine(x,42,x+18,42)
            p.setPen(QColor('#223846'));p.drawText(x+24,46,label);x+=p.fontMetrics().horizontalAdvance(label)+46
        times=[t for t,v in points];values=[v for t,v in points]
        records=self.plotted_records();count=len(records);low=min(0,min(values));high=max(0,max(values))
        padding=max((high-low)*.1,.001);maximum=high+padding;minimum=low-padding if low<0 else 0
        left,right,top,bottom=75,self.width()-65,65,self.height()-80
        if right<=left or bottom<=top:return
        def screen(index,v):
            return QPointF((left+right)/2 if count==1 else left+index/(count-1)*(right-left),bottom-(v-minimum)/(maximum-minimum)*(bottom-top))
        for i in range(5):
            value=minimum+(maximum-minimum)*i/4;y=screen(0,value).y()
            p.setPen(QPen(QColor('#dce5eb'),1));p.drawLine(QPointF(left,y),QPointF(right,y))
            p.setPen(QColor('#223846'));p.drawText(6,int(y)+4,f'{value:.3g}')
        p.setPen(QPen(QColor('#a5b5c0'),1));p.drawLine(left,top,left,bottom);p.drawLine(left,bottom,right,bottom)
        zero=screen(0,0).y();p.setPen(QPen(QColor('#9aaab5'),1,Qt.DashLine));p.drawLine(QPointF(left,zero),QPointF(right,zero))
        # A fixed label strip keeps plot geometry independent of dates and label count.
        date_font=QFont(p.font());date_font.setPixelSize(12);p.setFont(date_font)
        max_labels=max(2,int((right-left)/22));step=max(1,(count+max_labels-1)//max_labels)
        indices=list(range(0,count,step))
        if indices[-1]!=count-1:indices.append(count-1)
        p.setPen(QColor('#223846'))
        for index in indices:
            label=datetime.fromisoformat(records[index].created_at).astimezone().strftime('%Y/%m/%d')
            p.save();p.translate(screen(index,0).x(),bottom+7);p.rotate(45);p.drawText(0,12,label);p.restore()
        for label,color,items in series:
            scaled=[screen(index,v) for index,(t,v) in enumerate(items)];p.setPen(QPen(QColor(color),2));p.setBrush(QColor(color))
            for a,b in zip(scaled,scaled[1:]):p.drawLine(a,b)
            for point in scaled:p.drawEllipse(point,3,3)
            selected=next((r for r in records if r.id==self.highlight_id),None)
            if selected:
                index=next(i for i,r in enumerate(records) if r.id==self.highlight_id)
                # Identify the record directly when multiple measurements share a timestamp.
                m=selected.result.selected
                if m and selected.result.center_method==self.center_method and m.unit==self.unit:
                    value=(m.max_distance if self.center_method=='intersection_centroid' else m.circle.radius) if radius else {'直線距離':m.laser_distance,'X成分（右が正）':m.laser_delta.x,'Y成分（上が正）':m.laser_delta.y}[label]
                    p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor(color),2));p.drawEllipse(screen(index,value),6,6)


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
        self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(['日時','画像名','装置','軸','有効帯数','広がり指標','中心偏位（レーザー中心基準）','方式'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True); self.table.itemSelectionChanged.connect(self.show_detail); root.addWidget(self.table)
        self.detail=QLabel('記録を選択してください'); self.detail.setWordWrap(True); root.addWidget(self.detail)
        tools=QHBoxLayout()
        for label,action in [('一覧をCSV出力',self.export_csv),('選択記録をPDF出力',self.export_pdf),('選択記録を再度開く',self.reopen),('選択記録を削除',self.delete)]:
            b=QPushButton(label); b.clicked.connect(action); tools.addWidget(b)
        root.addLayout(tools)
        options=QHBoxLayout(); self.metric_selector=QComboBox(); self.metric_selector.addItem('偏位','laser_distance'); self.metric_selector.addItem('最大距離','radius')
        self.method=QComboBox()
        for value,label in METHODS.items(): self.method.addItem(label,value)
        self.method.setCurrentIndex(self.method.findData('intersection_centroid'))
        options.addWidget(self.method)
        self.unit=QComboBox(); self.unit.addItems(['mm','px']); options.addWidget(QLabel('トレンド')); options.addWidget(self.metric_selector); options.addWidget(self.unit); options.addStretch(); root.addLayout(options)
        self.trend=TrendPlot(); root.addWidget(self.trend)
        self.method.currentIndexChanged.connect(self.update_trend)
        self.metric_selector.currentIndexChanged.connect(self.update_trend); self.unit.currentIndexChanged.connect(self.update_trend)
        self.refresh()
    def refresh(self,*args):
        from fistar.storage.repository import list_axes
        chosen=self.axis.currentData();self.axis.blockSignals(True);self.axis.clear();self.axis.addItem('全ての軸',None)
        names={a['id']:a['name'] for a in list_axes(self.connection)}
        for record in list_measurements(self.connection):names.setdefault(record.axis,record.snapshot.get('axis_definition',{}).get('name',AXES.get(record.axis,record.axis)))
        for key,name in names.items():self.axis.addItem(name,key)
        self.axis.setCurrentIndex(max(0,self.axis.findData(chosen)));self.axis.blockSignals(False)
        selected=self.device.currentData(); self.device.blockSignals(True); self.device.clear(); self.device.addItem('全ての装置',None)
        for device in list_record_devices(self.connection): self.device.addItem(device,device)
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
            values=[datetime.fromisoformat(record.created_at).astimezone().strftime('%Y/%m/%d %H:%M'),record.image_name,record.device,record.snapshot.get('axis_definition',{}).get('name',AXES.get(record.axis,record.axis)),str(len(record.result.active_spoke_ids)),('最大交点距離 ' if centroid else '半径 ')+f'{spread:.4f} {m.unit}',f'{m.laser_distance:.4f} {m.unit}',METHODS[record.result.center_method]]
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
            self.detail.setText(f'交点重心方式\n交点 {len(m.intersections)}個 ／ 計算不能ペア {len(m.skipped_pairs)}組\n実画像の臨床的精度は未検証'); return
        self.detail.setText(f'校正：{c["source"] if c else "未校正"} ／ 有効帯 {len(r.result.active_spoke_ids)}本 ／ チャンネル {r.snapshot.get("channel","—")}\n実画像の臨床的精度は未検証')
    def update_trend(self):
        self.trend.center_method=self.method.currentData()
        index=self.metric_selector.findData('radius')
        self.metric_selector.setItemText(index,'最大距離' if self.trend.center_method=='intersection_centroid' else '最大半径')
        self.trend.records=self.records; self.trend.unit=self.unit.currentText(); self.trend.metric_name=self.metric_selector.currentData()
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
        if not r:return
        dialog=QInputDialog(self);dialog.setWindowTitle('PDFレポート');dialog.setLabelText('コメント（任意・500文字まで／記録には保存しません）');dialog.setOption(QInputDialog.UsePlainTextEditForTextInput,True);dialog.resize(500,250)
        if dialog.exec()!=QDialog.Accepted:return
        comment=dialog.textValue()
        if len(comment)>500:QMessageBox.warning(self,'コメント','コメントは500文字以内で入力してください');return
        path,_=QFileDialog.getSaveFileName(self,'PDFレポートを保存','fistar.pdf','PDF (*.pdf)')
        if not path:return
        try:
            from fistar.exporting import export_pdf
            since=until=None;period='全期間'
            if self.date_filter.isChecked():
                since=datetime.combine(self.since.date().toPython(),datetime.min.time()).astimezone().isoformat()
                until=datetime.combine(self.until.date().toPython()+timedelta(days=1),datetime.min.time()).astimezone().isoformat()
                period=self.since.date().toString('yyyy/MM/dd')+'–'+self.until.date().toString('yyyy/MM/dd')
            candidates=list_measurements(self.connection,device=r.device,axis=r.axis,since=since,until=until)
            from fistar.pdf_report import select_trend_records
            export_pdf(r,path,comment,select_trend_records(r,candidates),period_label=period)
        except Exception as error:QMessageBox.warning(self,'出力できません',str(error))
