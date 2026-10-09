"""Delayed, compact help that stays visible while hovering."""
from PySide6.QtCore import QObject,QEvent,Qt,QPoint,QTimer
from PySide6.QtWidgets import QFrame,QLabel,QVBoxLayout,QWidget

class HoverHelp(QObject):
    def __init__(self,targets,text,parent,delay_ms=1000):
        super().__init__(parent);self.target=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(delay_ms);self.timer.timeout.connect(self.show_popup)
        self.popup=QFrame(parent,Qt.ToolTip)
        self.popup.setAttribute(Qt.WA_ShowWithoutActivating)
        self.popup.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.popup.setObjectName('hoverHelp')
        self.popup.setStyleSheet('QFrame#hoverHelp { background: #253b49; border: 1px solid #526976; border-radius: 5px; } QLabel { color: white; background: transparent; border: none; }')
        layout=QVBoxLayout(self.popup);layout.setContentsMargins(10,8,10,8)
        label=QLabel(text);label.setWordWrap(True);label.setFixedWidth(280);layout.addWidget(label)
        for target in targets:target.setToolTip('');target.installEventFilter(self)
    def show_popup(self):
        target=self.target
        if target is None or not target.isVisible():return
        self.popup.adjustSize();position=target.mapToGlobal(QPoint(0,target.height()+6));available=target.screen().availableGeometry()
        x=max(available.left(),min(position.x(),available.right()-self.popup.width()+1));y=position.y()
        if y+self.popup.height()>available.bottom()+1:y=target.mapToGlobal(QPoint(0,0)).y()-self.popup.height()-6
        self.popup.move(x,max(available.top(),y));self.popup.show()
    def eventFilter(self,target,event):
        if event.type()==QEvent.Enter:
            self.target=target;self.popup.hide();self.timer.start()
        elif event.type() in (QEvent.Leave,QEvent.Hide,QEvent.MouseButtonPress,QEvent.Wheel):
            if self.target is target:self.timer.stop();self.target=None;self.popup.hide()
        elif event.type()==QEvent.ToolTip:return True
        return super().eventFilter(target,event)


def bind_tooltips(parent):
    """Convert existing tooltips to the same delayed, persistent help style."""
    return [HoverHelp((widget,),widget.toolTip(),parent) for widget in parent.findChildren(QWidget) if widget.toolTip()]
