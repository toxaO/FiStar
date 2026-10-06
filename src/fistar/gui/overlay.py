"""View-only overlay options and screen-space label placement."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QFont,QFontMetricsF
from PySide6.QtWidgets import QWidget,QGridLayout,QCheckBox

LABELS={'laser':'レーザー点','search_circle':'探索円','detection_points':'検出点','lines':'中心線','band_labels':'帯番号','intersections':'交点','intersection_labels':'交点ラベル','center':'推定中心','evaluation_circle':'評価円','offset':'偏位線'}
DEFAULTS={key:key!='intersection_labels' for key in LABELS}
DETAIL_DEFAULTS={**DEFAULTS,'image':True,'band_labels':False,'intersection_labels':True,'search_circle':False,'detection_points':False,'evaluation_circle':False,'offset':False}

class OverlayControls(QWidget):
    def __init__(self,view,parent=None):
        super().__init__(parent); layout=QGridLayout(self); self.checks={}
        labels=({'image':'画像',**LABELS} if 'image' in view.visibility else LABELS)
        for i,(key,label) in enumerate(labels.items()):
            check=QCheckBox(label); check.setChecked(view.visibility[key]); self.checks[key]=check
            check.toggled.connect(lambda checked,k=key:view.set_visibility(k,checked))
            layout.addWidget(check,i//3,i%3)

def overlay_font():
    font=QFont(); font.setPixelSize(12); return font

def label_layout(points,viewport,occupied=()):
    """Group identical coordinates and place labels without moving true points."""
    metrics=QFontMetricsF(overlay_font()); groups={}
    for point,text in points:
        key=(round(point.x(),9),round(point.y(),9))
        if key not in groups: groups[key]=[point,[]]
        groups[key][1].append(text)
    placed=[]; used=list(occupied)
    anchors=[QRectF(p.x()-4,p.y()-4,8,8) for p,_ in groups.values()]
    bounds=QRectF(viewport).adjusted(4,4,-4,-4)
    for point,texts in groups.values():
        if not bounds.contains(point): continue
        text=', '.join(texts)
        box=metrics.boundingRect(QRectF(0,0,210,10000),Qt.TextWordWrap,text)
        width,height=box.width()+10,box.height()+6
        chosen=None
        for radius in range(14,650,14):
            for dx,dy in ((1,-1),(1,1),(-1,-1),(-1,1),(0,-1),(0,1),(1,0),(-1,0)):
                x=point.x()+dx*radius-(width if dx<0 else width/2 if dx==0 else 0)
                y=point.y()+dy*radius-(height if dy<0 else height/2 if dy==0 else 0)
                rect=QRectF(x,y,width,height)
                if bounds.contains(rect) and not any(rect.adjusted(-3,-3,3,3).intersects(r) for r in (*used,*anchors)):
                    chosen=rect; break
            if chosen is not None: break
        if chosen is not None:
            used.append(chosen); placed.append((point,text,chosen))
    return placed


from dataclasses import dataclass
import math

@dataclass(frozen=True)
class DetailFit:
    center: QPointF
    scale: float
    viewport_center: QPointF
    reserved: tuple[QRectF, ...]
    label_count: int
    def map(self,point):
        return QPointF((point.x()-self.center.x())*self.scale+self.viewport_center.x(),
                      (point.y()-self.center.y())*self.scale+self.viewport_center.y())

def auto_fit_detail(points,label_points,viewport,band_points=()):
    """Fit all mandatory points and labels to a requested image/view size."""
    viewport=QRectF(viewport)
    if not points or viewport.width()<=64 or viewport.height()<=64:
        raise ValueError('全点を収めるための表示領域が不足しています')
    if not all(math.isfinite(v) for p in points for v in (p.x(),p.y())):
        raise ValueError('表示対象の点が不正です')
    left,right=min(p.x() for p in points),max(p.x() for p in points)
    top,bottom=min(p.y() for p in points),max(p.y() for p in points)
    center=QPointF(left/2+right/2,top/2+bottom/2)
    width,height=right-left,bottom-top
    scale=min((viewport.width()-64)/width if width else math.inf,
              (viewport.height()-64)/height if height else math.inf)
    if not math.isfinite(scale): scale=min(viewport.width(),viewport.height())/4
    def candidate(value):
        fit=DetailFit(center,value,viewport.center(),(),0)
        mapped=[fit.map(p) for p in points]
        reserved=tuple(QRectF(p.x()-8,p.y()-8,16,16) for p in mapped)
        mapped_labels=[(fit.map(p),text) for p,text in label_points]
        required=len({(round(p.x(),9),round(p.y(),9)) for p,_ in mapped_labels})
        fit=DetailFit(center,value,viewport.center(),reserved,required)
        bands=label_layout([(fit.map(p),text) for p,text in band_points],viewport,reserved)
        labels=label_layout(mapped_labels,viewport,(*reserved,*(rect for _,_,rect in bands)))
        return fit if len(labels)==required else None
    # Start with the largest geometric fit; reduce only for label clearance.
    failed=None
    for _ in range(50):
        fit=candidate(scale)
        if fit is not None:
            if failed is not None:
                low,high=scale,failed
                for _ in range(8):
                    mid=(low+high)/2; refined=candidate(mid)
                    if refined is not None: low=mid;fit=refined
                    else: high=mid
            return fit
        failed=scale;scale*=.9
    raise ValueError('この画像サイズでは全交点ラベルを配置できません。ウィンドウを広げて縮尺リセットを押してください')
