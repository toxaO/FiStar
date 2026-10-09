from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QGroupBox,QVBoxLayout,QFormLayout,QLineEdit,QListWidget,QListWidgetItem,QHBoxLayout,QPushButton,QMessageBox
from fistar.storage.repository import list_axes,save_axis,remove_axis

class AxisSettings(QGroupBox):
    changed=Signal()
    def __init__(self,connection):
        super().__init__('回転軸・方向ラベル');self.connection=connection;self.key=None;self.setMaximumWidth(480)
        layout=QHBoxLayout(self);layout.setContentsMargins(10,8,10,10);layout.setSpacing(12)
        self.items=QListWidget();self.items.setFixedWidth(110);layout.addWidget(self.items)
        editor=QVBoxLayout();editor.setSpacing(8);layout.addLayout(editor)
        form=QFormLayout();self.fields={}
        for key,label in [('name','軸名'),('top','上'),('bottom','下'),('left','左'),('right','右')]:
            field=QLineEdit();field.setToolTip('軸の表示名を入力します。' if key=='name' else f'画像の{label}側に表示する方向ラベルです。');self.fields[key]=field;form.addRow(label,field)
        form.setHorizontalSpacing(12);form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);form.setVerticalSpacing(6);editor.addLayout(form);editor.addStretch()
        buttons=QVBoxLayout();buttons.setSpacing(8);layout.addLayout(buttons)
        for text,callback in [('新規',self.new),('追加・変更を保存',self.save),('削除',self.delete)]:
            button=QPushButton(text);button.setToolTip({'新規':'新しい軸の入力欄を準備します。','追加・変更を保存':'軸名と方向ラベルを登録・更新します。','削除':'選択した軸を削除します。過去記録は残ります。'}[text]);button.clicked.connect(callback);buttons.addWidget(button)
        buttons.addStretch()
        self.items.currentItemChanged.connect(self.select);self.reload()
    def reload(self):
        self.items.blockSignals(True);self.items.clear()
        for axis in list_axes(self.connection):
            item=QListWidgetItem(axis['name']);item.setData(Qt.UserRole,axis);self.items.addItem(item)
        self.items.blockSignals(False)
    def select(self,item,previous=None):
        if not item:return
        axis=item.data(Qt.UserRole);self.key=axis['id']
        for key,field in self.fields.items():field.setText(axis[key])
    def new(self):
        self.key=None;self.items.clearSelection()
        for field in self.fields.values():field.clear()
        self.fields['name'].setFocus()
    def save(self):
        try:save_axis(self.connection,self.key,**{key:field.text() for key,field in self.fields.items()})
        except ValueError as error:QMessageBox.warning(self,'回転軸',str(error));return
        self.reload();self.new();self.changed.emit()
    def delete(self):
        if not self.key:return
        try:remove_axis(self.connection,self.key)
        except ValueError as error:QMessageBox.warning(self,'回転軸',str(error));return
        self.reload();self.new();self.changed.emit()
