from pathlib import Path
import math
from PySide6.QtCore import Qt,QRectF,QSize,QPointF,QTimer
from PySide6.QtGui import QIcon,QPainter,QColor
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QToolButton,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QSplitter,QScrollArea
from .image_view import ImageView
from .hover_help import bind_tooltips
from .overlay import DETAIL_DEFAULTS,OverlayControls,auto_fit_detail

class ScaleBar(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(96,18)
    def paintEvent(self,event):
        painter=QPainter(self); painter.setPen(QColor('#233846'))
        painter.drawLine(8,9,88,9)
        for x in (8,88): painter.drawLine(x,4,x,14)

class SquareImagePanel(QWidget):
    """Keep the image view square within the available left pane."""
    def __init__(self,view,alignment=Qt.AlignHCenter):
        super().__init__(); self.view=view;self.alignment=alignment; self.setMinimumSize(280,280)
        view.setParent(self); view.show()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        side=min(self.width(),self.height())
        x=self.width()-side if self.alignment==Qt.AlignRight else (self.width()-side)//2
        self.view.setGeometry(x,(self.height()-side)//2,side,side)
        if not self.view.read_only and self.view._fit_full_image:self.view.reset_view()

class CenterDetail(QDialog):
    """Non-modal, read-only view. Display state never touches the analysis."""
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('中心付近の拡大'); self.resize(1280,850)
        self._auto_fit_active=True; self._fit_pending=False; self._fitting=False
        self.image_key=None; self.view=ImageView(); self.view.read_only=True
        self.view.visibility=dict(DETAIL_DEFAULTS)
        self.view.reset_callback=self.center_on_result
        root=QVBoxLayout(self); tools=QHBoxLayout(); self.buttons={}
        icons=Path(__file__).parent/'assets/icons/tools'
        reset=QToolButton();reset.setProperty('imageTool',True);reset.setIcon(QIcon(str(icons/'tools_reset.png')));reset.setIconSize(QSize(24,24));reset.setToolTip('全点を収める（縮尺リセット）');reset.setAccessibleName('全点を収める');reset.clicked.connect(self.center_on_result);tools.addWidget(reset)
        self.reset_tool_button=reset
        self.scale_bar=ScaleBar(); tools.addWidget(self.scale_bar)
        self.scale_label=QLabel(); tools.addWidget(self.scale_label); tools.addStretch(); root.addLayout(tools)
        self.controls=OverlayControls(self.view)
        for check in self.controls.checks.values(): check.toggled.connect(self.schedule_fit)
        self.splitter=QSplitter(Qt.Horizontal)
        self.image_panel=SquareImagePanel(self.view); self.splitter.addWidget(self.image_panel)
        sidebar=QWidget(); sidebar.setMinimumWidth(360); side_layout=QVBoxLayout(sidebar)
        side_layout.setContentsMargins(6,0,0,0)
        side_layout.addWidget(QLabel('交点一覧'))
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(['帯ペア','交点X','交点Y','選択した中心からの距離'])
        self.table.setAlternatingRowColors(True);self.table.setShowGrid(False);self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        side_layout.addWidget(self.table,1)
        side_layout.addWidget(QLabel('表示する項目'))
        self.controls_scroll=QScrollArea(); self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setWidget(self.controls); self.controls_scroll.setMinimumHeight(110); self.controls_scroll.setMaximumHeight(190)
        side_layout.addWidget(self.controls_scroll)
        self.splitter.addWidget(sidebar); self.splitter.setSizes([780,480])
        self.splitter.setStretchFactor(0,1); self.splitter.setStretchFactor(1,0)
        root.addWidget(self.splitter,1)
        root.addWidget(QLabel('確認専用。点・線の編集はできません。ラベルが表示しきれない交点は一覧で確認してください。'))
        self.fit_status=QLabel(); self.fit_status.setWordWrap(True); root.addWidget(self.fit_status)
        self.view.setMinimumSize(64,64)
        self.view.view_changed.connect(self.update_scale)
        self.view.viewport_resized.connect(self.schedule_fit)
        self.view.navigation_started.connect(self.manual_navigation)
        self.set_mode('pan')
        self.hover_helpers=bind_tooltips(self)
    def set_mode(self,mode):
        self.view.set_mode(mode)
        for name,button in self.buttons.items(): button.setChecked(name==mode)
    def sync(self,source):
        session=source.session
        if not session.image or not session.result or session.result.selected is None:
            self.close(); return
        if self.image_key is not None and self.image_key!=(session.image.sha256,str(session.image.path)):
            self.close(); return
        old_scene=self.view.sceneRect()
        old_transform=self.view.transform()
        old_center=self.view.mapToScene(self.view.viewport().rect()).boundingRect().center()
        first=self.image_key is None; self.image_key=(session.image.sha256,str(session.image.path))
        self.view.set_session(session)
        self.view.set_display_range(source.display_low,source.display_high)
        center=self.view.selected_center(); h,w=session.image.raw.shape[:2]
        region=QRectF(0,0,w,h).united(QRectF(center.x()-4096,center.y()-4096,8192,8192))
        self.view.setSceneRect(region if first else region.united(old_scene))
        if not first: self.view.setTransform(old_transform); self.view.centerOn(old_center)
        m=session.result.selected; chosen=m.center if session.center_method=='intersection_centroid' else m.circle.center
        self.table.setRowCount(len(self.view.intersection_data()))
        for row,(_,text,intersection) in enumerate(self.view.intersection_data()):
            p=intersection.point
            distance=math.hypot(p.x-chosen.x,p.y-chosen.y)
            values=(text,f'{p.x:.6f} {m.unit}',f'{p.y:.6f} {m.unit}',f'{distance:.6f} {m.unit}')
            for col,value in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(value))
        self.update_scale()
        if self._auto_fit_active: self.schedule_fit()
    def manual_navigation(self):
        self._auto_fit_active=False
        self.fit_status.setText('手動表示中。縮尺リセットで全点が収まる自動配置に戻せます。')
    def schedule_fit(self):
        if self._auto_fit_active and not self._fit_pending and not self._fitting:
            self._fit_pending=True; QTimer.singleShot(0,self.deferred_fit)
    def deferred_fit(self):
        self._fit_pending=False
        if self.isVisible() and self._auto_fit_active: self.fit_all_points()
    def center_on_result(self):
        self._auto_fit_active=True; self.fit_all_points(); self.schedule_fit()
    def fit_all_points(self):
        center=self.view.selected_center()
        if center is None or self._fitting: return
        self._fitting=True
        try:
            s=self.view.session; points=[center]
            if s.laser: points.append(QPointF(s.laser.x,s.laser.y))
            labels=[(p,text) for p,text,_ in self.view.intersection_data()]
            points.extend(p for p,_ in labels)
            bands=[]
            if self.view.visibility['band_labels']:
                for i,spoke in enumerate(s.spokes,1):
                    point=self.view.endpoints(spoke)[0];bands.append((QPointF(point.x,point.y),str(i)))
            fit=auto_fit_detail(points,labels,self.view.viewport().rect(),band_points=bands)
            h,w=s.image.raw.shape[:2]
            extent=QRectF(fit.center.x()-self.view.viewport().width()/fit.scale,
                         fit.center.y()-self.view.viewport().height()/fit.scale,
                         2*self.view.viewport().width()/fit.scale,2*self.view.viewport().height()/fit.scale)
            self.view.setSceneRect(QRectF(0,0,w,h).united(extent))
            self.view.resetTransform();self.view.scale(fit.scale,fit.scale);self.view.centerOn(fit.center)
            status='全交点・レーザー点・推定中心と交点ラベルを収めた表示です。'
            if not labels:
                status=('交点情報を表示できません：'+s.result.centroid_error if s.result.centroid_error else 'この記録には交点情報がありません。交点重心方式を選択して追加計算してください。')
            self.fit_status.setText(status)
            self.view.viewport().update();self.update_scale()
        except ValueError as error:
            self.fit_status.setText(str(error))
        finally: self._fitting=False
    def update_scale(self):
        if not hasattr(self,'scale_label'): return
        scale=self.view.transform().m11()
        if scale<=0: return
        pixels=80/scale
        text=f'画面80px ≈ 原画像 {pixels:.3g} px'
        s=self.view.session
        if s and s.calibration:
            text+=f' ／ X {pixels*s.calibration.sx_mm:.3g}, Y {pixels*s.calibration.sy_mm:.3g} mm'
        self.scale_label.setText(text)
