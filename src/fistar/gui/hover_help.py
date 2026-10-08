"""マウスを置いている間だけ表示する、時間制限のない説明枠。"""
from PySide6.QtCore import QObject,QEvent,Qt,QPoint
from PySide6.QtWidgets import QFrame,QLabel,QVBoxLayout

class HoverHelp(QObject):
    def __init__(self,targets,text,parent):
        super().__init__(parent)
        self.popup=QFrame(parent,Qt.ToolTip)
        self.popup.setAttribute(Qt.WA_ShowWithoutActivating)
        self.popup.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.popup.setObjectName('hoverHelp')
        self.popup.setStyleSheet('QFrame#hoverHelp { background: #253b49; border: 1px solid #526976; border-radius: 5px; } QLabel { color: white; background: transparent; border: none; }')
        layout=QVBoxLayout(self.popup);layout.setContentsMargins(12,10,12,10)
        label=QLabel(text);label.setWordWrap(True);label.setFixedWidth(330);layout.addWidget(label)
        for target in targets:
            target.setToolTip('');target.installEventFilter(self)
    def eventFilter(self,target,event):
        if event.type()==QEvent.Enter:
            self.popup.adjustSize()
            position=target.mapToGlobal(QPoint(0,target.height()+6))
            available=target.screen().availableGeometry()
            x=max(available.left(),min(position.x(),available.right()-self.popup.width()+1))
            y=position.y()
            if y+self.popup.height()>available.bottom()+1:y=target.mapToGlobal(QPoint(0,0)).y()-self.popup.height()-6
            y=max(available.top(),y)
            self.popup.move(x,y);self.popup.show()
        elif event.type() in (QEvent.Leave,QEvent.Hide,QEvent.MouseButtonPress):
            self.popup.hide()
        elif event.type()==QEvent.ToolTip:
            return True
        return super().eventFilter(target,event)
