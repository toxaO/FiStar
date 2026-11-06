import math
import sys
import numpy as np
from PySide6.QtCore import Qt, Signal, QEvent, QPointF, QRectF
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QFont, QBrush, QPainter, QCursor
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QWidget
from .overlay import DEFAULTS, overlay_font, label_layout
from fistar.core.models import Point
from fistar.core.detection import search_radius
from fistar.core.imaging import analysis_channel, display_image

NAVIGATION_CONTROL_MODIFIER = Qt.MetaModifier if sys.platform == "darwin" else Qt.ControlModifier


class ImageView(QGraphicsView):
    laser_selected=Signal(object)
    laser_selection_finished=Signal()
    calibration_selected=Signal(object,object)
    ruler_selected=Signal(object,object)
    view_changed=Signal()
    viewport_resized=Signal()
    navigation_started=Signal()
    navigation_mode_changed=Signal()
    circle_measured=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.visibility=dict(DEFAULTS); self.read_only=False; self.reset_callback=None;self._fit_full_image=False
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor('#111d28'))
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setRenderHint(QPainter.Antialiasing,True)
        self.mode='pan'; self.session=None; self.selected_id=None
        self.ruler_points=()
        self._key=None; self._pending=None; self._overlay=[]
        self._values=None; self._image_item=None; self.display_low=0.; self.display_high=1.
        self._navigation_drag=None; self._navigation_position=None
        self._navigation_button=None
        self._zoom_start=None
        self._temporary_navigation=None
        self._circle=None
        self._circle_start=None
        self._ruler_endpoint=None
        self._zoom_cursor=QCursor(Qt.SizeVerCursor)
        self.set_mode('pan')
        QApplication.instance().installEventFilter(self)
    def set_mode(self,mode):
        mode=mode or 'pan'
        if mode not in ('pan','zoom','laser','calibration','ruler','circle'): raise ValueError('画像操作が不正です')
        if self.read_only and mode not in ('pan','zoom'): mode='pan'
        self.mode=mode; self._pending=None;self._laser_preview=None;self._laser_start=None
        self.viewport().update()
        self._cancel_navigation_drag()
        self._circle_start=None
        self._ruler_endpoint=None
        self.setDragMode(QGraphicsView.NoDrag)
        self._update_cursor()

    @property
    def effective_mode(self):
        return self._temporary_navigation or self.mode

    def _update_cursor(self):
        if self._navigation_drag=='pan':
            self.setCursor(Qt.ClosedHandCursor)
        elif self.effective_mode=='pan':
            self.setCursor(Qt.OpenHandCursor)
        elif self.effective_mode=='zoom':
            self.setCursor(self._zoom_cursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def _cancel_navigation_drag(self):
        self._navigation_drag=None
        self._navigation_position=None
        self._navigation_button=None
        self._zoom_start=None

    @staticmethod
    def _navigation_mode(modifiers):
        if modifiers & NAVIGATION_CONTROL_MODIFIER:
            return 'zoom'
        if modifiers & Qt.ShiftModifier:
            return 'pan'
        return None

    def _set_navigation_modifiers(self, modifiers):
        mode=self._navigation_mode(modifiers)
        if mode!=self._temporary_navigation:
            self._temporary_navigation=mode
            self._update_cursor()
            self.navigation_mode_changed.emit()

    def eventFilter(self, watched, event):
        kind=event.type()
        if kind==QEvent.ApplicationDeactivate or (kind==QEvent.WindowDeactivate and watched is self.window()):
            self._cancel_navigation_drag()
            self._set_navigation_modifiers(Qt.NoModifier)
            self._update_cursor()
        elif kind in (QEvent.KeyPress,QEvent.KeyRelease) and isinstance(watched,QWidget) and watched.window() is self.window() and self.isVisible():
            navigation_key=Qt.Key_Meta if sys.platform=='darwin' else Qt.Key_Control
            modifier={Qt.Key_Shift:Qt.ShiftModifier,navigation_key:NAVIGATION_CONTROL_MODIFIER}.get(event.key())
            if modifier is not None:
                modifiers=event.modifiers()
                self._set_navigation_modifiers(modifiers | modifier if kind==QEvent.KeyPress else modifiers & ~modifier)
        return super().eventFilter(watched,event)
    def set_session(self,session):
        self.session=session
        if session.image is None: return
        key=(session.image.sha256,'luminance')
        if key!=self._key:
            self.ruler_points=();self._pending=None
            self._circle=None
            self._circle_start=None
            self._ruler_endpoint=None
            self._cancel_navigation_drag()
            self.circle_measured.emit(None)
            values=analysis_channel(session.image)
            low,high=np.percentile(values,[.5,99.5])
            if high<=low: high=low+1
            self._values=values; self.display_low=float(low); self.display_high=float(high)
            pixels=display_image(values,float(low),float(high))
            if session.image.photometric=='MINISWHITE': pixels=255-pixels
            h,w=pixels.shape
            qimage=QImage(pixels.data,w,h,pixels.strides[0],QImage.Format_Grayscale8).copy()
            self.scene().clear(); self._overlay=[]
            self._image_item=self.scene().addPixmap(QPixmap.fromImage(qimage))
            self._image_item.setTransformationMode(Qt.FastTransformation)
            self._image_item.setVisible(self.visibility.get('image',True))
            self.scene().setSceneRect(0,0,w,h)
            self._key=key; self.reset_view()
        self.draw_overlay()
    def set_display_range(self,low,high):
        if not math.isfinite(low) or not math.isfinite(high) or high<=low:
            raise ValueError('表示上限は下限より大きくしてください')
        if self._values is None: return
        pixels=display_image(self._values,low,high); h,w=pixels.shape
        if self.session.image.photometric=='MINISWHITE': pixels=255-pixels
        qimage=QImage(pixels.data,w,h,pixels.strides[0],QImage.Format_Grayscale8).copy()
        self._image_item.setPixmap(QPixmap.fromImage(qimage))
        self.display_low=float(low); self.display_high=float(high)
        self.viewport().update()
    def auto_display(self):
        if self._values is not None:
            low,high=np.percentile(self._values,[.5,99.5])
            self.set_display_range(float(low),float(high) if high>low else float(low)+1)
    def reset_view(self):
        if self._image_item is None: return
        self.resetTransform(); self.setSceneRect(self._image_item.boundingRect())
        self.fitInView(self._image_item,Qt.KeepAspectRatio);self._fit_full_image=True
    def endpoints(self,spoke):
        s=self.session
        hub=s.laser or Point(s.image.raw.shape[1]/2,s.image.raw.shape[0]/2)
        l=spoke.line
        shift=l.offset-l.nx*hub.x-l.ny*hub.y
        mid=Point(hub.x+l.nx*shift,hub.y+l.ny*shift)
        length=search_radius(s.image.raw.shape,hub,s.detection_settings)
        return Point(mid.x-l.ny*length,mid.y+l.nx*length),Point(mid.x+l.ny*length,mid.y-l.nx*length)
    def _add(self,item):
        self._overlay.append(item); item.setZValue(1)
    def set_visibility(self,key,visible):
        self.visibility[key]=visible
        if key=='image' and self._image_item: self._image_item.setVisible(visible)
        self.draw_overlay()
    def selected_center(self):
        s=self.session
        if not s or not s.result or s.result.selected is None: return None
        m=s.result.selected
        center=m.center if s.center_method=='intersection_centroid' else m.circle.center
        sx=s.calibration.sx_mm if m.unit=='mm' else 1
        sy=s.calibration.sy_mm if m.unit=='mm' else 1
        return QPointF(center.x/sx,center.y/sy)
    def intersection_data(self):
        s=self.session
        if not s or not s.result: return ()
        m=s.result.centroid_physical or s.result.centroid_pixels
        if not m: return ()
        sx=s.calibration.sx_mm if m.unit=='mm' else 1
        sy=s.calibration.sy_mm if m.unit=='mm' else 1
        numbers={spoke.id:str(i+1) for i,spoke in enumerate(s.spokes)}
        return tuple((QPointF(p.point.x/sx,p.point.y/sy),'–'.join(numbers[id] for id in p.spoke_ids),p) for p in m.intersections)
    def draw_overlay(self):
        for item in self._overlay: self.scene().removeItem(item)
        self._overlay=[]
        s=self.session; v=self.visibility
        if not s or not s.image: return
        if v['search_circle']:
            p=s.laser or Point(s.image.raw.shape[1]/2,s.image.raw.shape[0]/2); r=search_radius(s.image.raw.shape,p,s.detection_settings)
            outline=QPen(QColor(20,29,38,190),4.5);outline.setCosmetic(True)
            self._add(self.scene().addEllipse(p.x-r,p.y-r,2*r,2*r,outline))
            pen=QPen(QColor('#ffd166'),2.5,Qt.DashLine); pen.setCosmetic(True)
            self._add(self.scene().addEllipse(p.x-r,p.y-r,2*r,2*r,pen))
        if v['lines']:
            for spoke in s.spokes:
                a,b=self.endpoints(spoke)
                color='#65717a' if spoke.excluded else '#ffc66d' if spoke.id==self.selected_id else '#39d8cf'
                pen=QPen(QColor(color),1,Qt.DashLine if spoke.excluded else Qt.SolidLine); pen.setCosmetic(True)
                self._add(self.scene().addLine(a.x,a.y,b.x,b.y,pen))
        if s.result and s.result.selected is not None:
            center=self.selected_center(); m=s.result.selected
            pen=QPen(QColor('#ff6262' if s.center_method=='intersection_centroid' else '#c181ff'),1); pen.setCosmetic(True)
            if v['evaluation_circle'] and s.center_method=='minimax':
                sx=s.calibration.sx_mm if m.unit=='mm' else 1; sy=s.calibration.sy_mm if m.unit=='mm' else 1
                rx,ry=m.circle.radius/sx,m.circle.radius/sy
                self._add(self.scene().addEllipse(center.x()-rx,center.y()-ry,2*rx,2*ry,pen))
            if v['offset'] and s.laser:
                self._add(self.scene().addLine(s.laser.x,s.laser.y,center.x(),center.y(),pen))
        if self._circle is not None:
            center,radius=self._circle
            pen=QPen(QColor('#51e1e3'),2);pen.setCosmetic(True)
            self._add(self.scene().addEllipse(center.x-radius,center.y-radius,2*radius,2*radius,pen))
        if self.ruler_points:
            pen=QPen(QColor('#ff78b5'),2);pen.setCosmetic(True)
            if len(self.ruler_points)==2:
                a,b=self.ruler_points;self._add(self.scene().addLine(a.x,a.y,b.x,b.y,pen))
        self.viewport().update()
    def drawForeground(self,painter,rect):
        s=self.session; v=self.visibility
        if not s or not s.image: return
        painter.save(); painter.resetTransform(); painter.setRenderHint(QPainter.Antialiasing,True)
        painter.setFont(overlay_font()); transform=self.viewportTransform()
        labels=getattr(s,'axis_definition',{})
        width=self.viewport().width();height=self.viewport().height()
        metrics=painter.fontMetrics()
        for key,x,y in [('top',width/2,20),('bottom',width/2,height-12),('left',24,height/2),('right',width-24,height/2)]:
            text=labels.get(key,'')
            if not text:continue
            tw=metrics.horizontalAdvance(text);th=metrics.height()
            x=max(tw/2+5,min(width-tw/2-5,x))
            painter.fillRect(int(x-tw/2-4),int(y-metrics.ascent()-3),tw+8,th+6,QColor('#17232d'))
            painter.setPen(QColor('#ffffff'));painter.drawText(QPointF(x-tw/2,y),text)
        def screen(p): return transform.map(QPointF(p.x,p.y))
        def marker(point,color,radius=3,shape='circle'):
            painter.setPen(QPen(QColor(color),1)); painter.setBrush(Qt.NoBrush)
            if shape=='cross':
                painter.drawLine(point+QPointF(-radius,0),point+QPointF(radius,0))
                painter.drawLine(point+QPointF(0,-radius),point+QPointF(0,radius))
            else: painter.drawEllipse(point,radius,radius)
        laser=self._laser_preview or s.laser
        if laser and (v['laser'] or self.mode=='laser'): marker(screen(laser),'#26d6ed',6,'cross')
        center=self.selected_center()
        if center is not None and v['center']:
            marker(transform.map(center),'#ff6262' if s.center_method=='intersection_centroid' else '#c181ff',7)
        if s.detection and v['detection_points']:
            for p in s.detection.points: marker(screen(p),'#ffc66d',2)
        bands=[]
        for number,spoke in enumerate(s.spokes,1):
            a,b=self.endpoints(spoke)
            if v['band_labels']: bands.append((screen(a),str(number)))
        data=self.intersection_data()
        occupied=[]
        if center is not None:
            q=transform.map(center); occupied.append(QRectF(q.x()-8,q.y()-8,16,16))
        if s.laser:
            q=screen(s.laser); occupied.append(QRectF(q.x()-8,q.y()-8,16,16))
        occupied.extend(QRectF(transform.map(p).x()-8,transform.map(p).y()-8,16,16) for p,_,_ in data)
        labels=label_layout(bands,self.viewport().rect(),occupied)
        occupied.extend(r for _,_,r in labels)
        intersection_labels=label_layout([(transform.map(p),text) for p,text,_ in data],self.viewport().rect(),occupied) if v['intersection_labels'] else []
        all_labels=(*labels,*intersection_labels)
        painter.setPen(QPen(QColor(228,236,242,120),1))
        for point,_,box in all_labels: painter.drawLine(point,box.center())
        for _,text,box in all_labels:
            painter.setPen(QPen(QColor('#e4ecf2'),1)); painter.setBrush(QColor('#111d28'))
            painter.drawRoundedRect(box,3,3)
            painter.drawText(box.adjusted(5,3,-5,-3),Qt.TextWordWrap,text)
        # True intersection positions are the last layer, ahead of all leaders.
        if v['intersections']:
            for point,_,_ in data:
                q=transform.map(point)
                marker(q,'#18252d',3,'cross'); marker(q,'#ffffff',1.5,'cross')
        for p in self.ruler_points:marker(screen(p),'#ff78b5',4,'cross')
        painter.restore()
    def _zoom_by(self,factor,center):
        if self._image_item is None: return
        self._fit_full_image=False
        new_scale=self.transform().m11()*factor
        self.reserve_view_center(center,new_scale)
        self.scale(factor,factor); self.centerOn(center); self.view_changed.emit()
    def reserve_view_center(self,center,scale):
        half_width=(self.viewport().width()/2+4)/scale
        half_height=(self.viewport().height()/2+4)/scale
        area=QRectF(center.x()-half_width,center.y()-half_height,2*half_width,2*half_height)
        self.setSceneRect(self.sceneRect().united(area))
    def zoom_in(self):
        self._zoom_by(1.1,self.mapToScene(self.viewport().rect()).boundingRect().center())
    def zoom_out(self):
        self._zoom_by(1/1.1,self.mapToScene(self.viewport().rect()).boundingRect().center())
    def _zoom_at(self,factor,position,anchor):
        scale=self.transform().m11()
        fit=min(self.viewport().width()/self._image_item.pixmap().width(),
                self.viewport().height()/self._image_item.pixmap().height())
        minimum=min(fit/16,scale)
        maximum=max(64.,fit*64,scale)
        new_scale=max(minimum,min(maximum,scale*factor))
        center=self.mapToScene(self.viewport().rect()).boundingRect().center()
        center=anchor+(center-self.mapToScene(position))*scale/new_scale
        self._zoom_by(new_scale/scale,center)

    def wheelEvent(self,event):
        if self._image_item is not None:
            position=event.position().toPoint()
            anchor=self.mapToScene(position)
            pixels=event.pixelDelta().y()
            angle=event.angleDelta().y()
            if (pixels or angle) and self._image_item.boundingRect().contains(anchor):
                self.navigation_started.emit()
                factor=math.pow(1.004,pixels) if pixels else math.pow(1.1,angle/120)
                self._zoom_at(factor,position,anchor)
        event.accept()

    def mouseDoubleClickEvent(self,event):
        self._cancel_navigation_drag()
        self._update_cursor()
        if self.reset_callback: self.reset_callback()
        else: self.reset_view()
        event.accept()

    def resizeEvent(self,event):
        super().resizeEvent(event); self.view_changed.emit(); self.viewport_resized.emit()
    def _point(self,event):
        p=self.mapToScene(event.position().toPoint())
        return Point(p.x(),p.y())
    def mousePressEvent(self,event):
        if not self.session or not self.session.image:
            return super().mousePressEvent(event)
        temporary=self._navigation_mode(event.modifiers())
        mac_control_click=sys.platform=='darwin' and event.button()==Qt.RightButton and temporary=='zoom'
        if event.button()!=Qt.LeftButton and not mac_control_click:
            return super().mousePressEvent(event)
        self._set_navigation_modifiers(event.modifiers())
        if self.effective_mode in ('pan','zoom'):
            self.navigation_started.emit()
            self._navigation_drag=self.effective_mode
            self._navigation_position=event.position()
            self._navigation_button=event.button()
            if self._navigation_drag=='zoom':
                position=event.position().toPoint()
                self._zoom_start=(position,self.mapToScene(position))
            self._update_cursor()
            event.accept()
            return
        if self.read_only:
            event.accept()
            return

        p=self._point(event)
        if not self._image_item.boundingRect().contains(QPointF(p.x,p.y)):
            return
        if self.mode=='laser':
            self._laser_start=p
            self._laser_preview=p
            self.viewport().update()
        elif self.mode=='circle':
            self._circle_start=p
            self._circle=None
            self.circle_measured.emit(None)
            self.draw_overlay()
        elif self.mode in ('calibration','ruler'):
            if self.mode=='ruler' and len(self.ruler_points)==2:
                scale=self.transform().m11()
                distances=[math.hypot(p.x-point.x,p.y-point.y) for point in self.ruler_points]
                index=distances.index(min(distances))
                if distances[index]*scale<=8:
                    point=self.ruler_points[index]
                    self._ruler_endpoint=(index,p,point)
                    event.accept()
                    return
            if self._pending is None:
                self._pending=p
                if self.mode=='ruler':
                    self.ruler_points=(p,)
                    self.draw_overlay()
                    self.view_changed.emit()
            else:
                first=self._pending
                self._pending=None
                if self.mode=='ruler':
                    self.ruler_points=(first,p)
                    self.draw_overlay()
                    self.ruler_selected.emit(first,p)
                else:
                    self.calibration_selected.emit(first,p)
        event.accept()

    def _update_circle(self,point):
        center=self._circle_start
        radius=math.hypot(point.x-center.x,point.y-center.y)
        self._circle=(center,radius) if radius else None
        self.draw_overlay()

    def circle_mean(self):
        if self._circle is None:
            return None
        center,radius=self._circle
        height,width=self._values.shape
        # Scene coordinates are pixel edges, so sample at pixel centers.
        cx,cy=center.x-.5,center.y-.5
        left=max(0,math.ceil(cx-radius))
        right=min(width,math.floor(cx+radius)+1)
        top=max(0,math.ceil(cy-radius))
        bottom=min(height,math.floor(cy+radius)+1)
        y,x=np.ogrid[top:bottom,left:right]
        mask=(x-cx)**2+(y-cy)**2<=radius**2
        values=self._values[top:bottom,left:right][mask]
        return float(values.mean(dtype=np.float64)) if values.size else None

    def _move_ruler_endpoint(self,point):
        index,start,original=self._ruler_endpoint
        target=Point(original.x+(point.x-start.x),original.y+(point.y-start.y))
        if self._image_item.boundingRect().contains(QPointF(target.x,target.y)):
            points=list(self.ruler_points)
            points[index]=target
            self.ruler_points=tuple(points)
            self.draw_overlay()

    def mouseMoveEvent(self,event):
        if self._navigation_drag:
            delta=event.position()-self._navigation_position
            if self._navigation_drag=='zoom' and delta.y():
                position,anchor=self._zoom_start
                self._zoom_at(math.pow(1.004,max(-175,min(175,-delta.y()))),position,anchor)
            elif self._navigation_drag=='pan' and not delta.isNull():
                self._fit_full_image=False
                scale=self.transform().m11()
                center=self.mapToScene(self.viewport().rect()).boundingRect().center()-delta/scale
                self.reserve_view_center(center,scale)
                self.centerOn(center)
                self.view_changed.emit()
            self._navigation_position=event.position()
        elif self._circle_start is not None:
            self._update_circle(self._point(event))
        elif self._ruler_endpoint is not None:
            self._move_ruler_endpoint(self._point(event))
        elif self._laser_start is None:
            return super().mouseMoveEvent(event)
        event.accept()

    def mouseReleaseEvent(self,event):
        if self._navigation_drag and event.button()==self._navigation_button:
            self._cancel_navigation_drag()
            self._set_navigation_modifiers(event.modifiers())
            self._update_cursor()
        elif event.button()!=Qt.LeftButton:
            return super().mouseReleaseEvent(event)
        elif self.mode=='laser' and self._laser_start is not None:
            point=self._point(event)
            moved=math.hypot(point.x-self._laser_start.x,point.y-self._laser_start.y)*self.transform().m11()>3
            self._laser_start=None;self._laser_preview=None
            if not moved and self._image_item.boundingRect().contains(QPointF(point.x,point.y)):self.laser_selected.emit(point)
            self.laser_selection_finished.emit()
            self.viewport().update()
        elif self._circle_start is not None:
            self._update_circle(self._point(event))
            self._circle_start=None
            self.circle_measured.emit(self.circle_mean())
        elif self._ruler_endpoint is not None:
            index,_,original=self._ruler_endpoint
            self._move_ruler_endpoint(self._point(event))
            self._ruler_endpoint=None
            if self.ruler_points[index]!=original:
                self.ruler_selected.emit(*self.ruler_points)
        else:
            return super().mouseReleaseEvent(event)
        event.accept()
