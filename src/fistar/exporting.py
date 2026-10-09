import csv
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPdfWriter,QPainter,QFont,QFontDatabase,QRawFont,QFontMetricsF,QPageSize,QColor
from PySide6.QtWidgets import QApplication
from fistar.gui.analysis_panel import AXES,METHODS

@contextmanager
def atomic_output(path):
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix='.fistar-',suffix=path.suffix,dir=path.parent)
    os.close(fd); temporary=Path(name)
    try:
        yield temporary
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()

CSV_HEADERS=['記録ID','日時','画像名','装置名','軸','単位','半径','中心偏位（レーザー中心基準）','偏位X','偏位Y','中心X','中心Y','有効帯数','中心推定方式','交点までの最大距離','使用交点数','計算不能ペア数','警告']

def export_csv(records,path):
    with atomic_output(path) as temporary:
        with temporary.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(CSV_HEADERS)
            for r in records:
                m=r.result.selected; centroid=r.result.center_method=='intersection_centroid'
                center=m.center if centroid else m.circle.center
                writer.writerow([r.id,r.created_at,r.image_name,r.device,r.snapshot.get('axis_definition',{}).get('name',AXES.get(r.axis,r.axis)),m.unit,'' if centroid else m.circle.radius,m.laser_distance,m.laser_delta.x,m.laser_delta.y,center.x,center.y,len(r.result.active_spoke_ids),METHODS[r.result.center_method],m.max_distance if centroid else '',len(m.intersections) if centroid else '',len(m.skipped_pairs) if centroid else '', '／'.join(m.warnings) if centroid else ''])

def japanese_font():
    candidates=['Hiragino Sans','Yu Gothic','Meiryo','Noto Sans CJK JP','Noto Sans JP']+QFontDatabase.families()
    for family in dict.fromkeys(candidates):
        font=QFont(family,11)
        raw=QRawFont.fromFont(font)
        if raw.isValid() and all(raw.supportsCharacter(ord(c)) for c in '日本語あ軸偏位'):
            return font
    raise ValueError('日本語対応フォントが見つかりません。日本語フォントを導入してください')

def export_pdf(record,path,comment="",trend_records=(),period_label="",data_dir=None):
    if QApplication.instance() is None:raise ValueError('PDF出力には起動中のQtアプリケーションが必要です')
    from .pdf_report import write_report
    with atomic_output(path) as temporary:
        write_report(record,temporary,japanese_font(),comment,trend_records,period_label,data_dir)
        if temporary.stat().st_size==0:raise OSError('PDFが空です')
