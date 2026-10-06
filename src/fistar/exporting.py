import csv
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPdfWriter,QPainter,QFont,QFontDatabase,QRawFont,QFontMetricsF,QPageSize,QColor
from PySide6.QtWidgets import QApplication
from fistar.gui.analysis_panel import AXES,STATUS,METHODS

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

CSV_HEADERS=['記録ID','日時','画像名','装置名','軸','単位','半径','レーザー偏位','偏位X','偏位Y','中心X','中心Y','有効帯数','許容値単位','半径許容値','偏位許容値','半径評価','偏位評価','中心推定方式','交点までの最大距離','使用交点数','計算不能ペア数','警告']

def export_csv(records,path):
    with atomic_output(path) as temporary:
        with temporary.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream); writer.writerow(CSV_HEADERS)
            for r in records:
                m=r.result.selected; centroid=r.result.center_method=='intersection_centroid'
                center=m.center if centroid else m.circle.center
                writer.writerow([r.id,r.created_at,r.image_name,r.device,AXES[r.axis],m.unit,'' if centroid else m.circle.radius,m.laser_distance,m.laser_delta.x,m.laser_delta.y,center.x,center.y,len(r.result.active_spoke_ids),r.limits.unit,r.limits.radius,r.limits.laser_distance,STATUS[r.judgment.radius],STATUS[r.judgment.laser_distance],METHODS[r.result.center_method],m.max_distance if centroid else '',len(m.intersections) if centroid else '',len(m.skipped_pairs) if centroid else '', '／'.join(m.warnings) if centroid else ''])

def japanese_font():
    candidates=['Hiragino Sans','Yu Gothic','Meiryo','Noto Sans CJK JP','Noto Sans JP']+QFontDatabase.families()
    for family in dict.fromkeys(candidates):
        font=QFont(family,11)
        raw=QRawFont.fromFont(font)
        if raw.isValid() and all(raw.supportsCharacter(ord(c)) for c in '日本語あ軸偏位'):
            return font
    raise ValueError('日本語対応フォントが見つかりません。日本語フォントを導入してください')

def export_pdf(record,path):
    if QApplication.instance() is None: raise ValueError('PDF出力には起動中のQtアプリケーションが必要です')
    font=japanese_font(); r=record; m=r.result.primary
    calibration=r.snapshot.get('calibration')
    calibration_text=(f'{calibration["source"]} / X {calibration["sx_mm"]:.6g}, Y {calibration["sy_mm"]:.6g} mm/px' if calibration else '未校正（pxで評価）')
    limit=lambda value: '未設定' if value is None else f'{value:.6g} {r.limits.unit}'
    fields=[('装置',r.device),('回転軸',AXES[r.axis]),('測定日時',datetime.fromisoformat(r.created_at).astimezone().strftime('%Y/%m/%d %H:%M:%S %z')),('画像名',r.image_name),('距離校正',calibration_text),('解析',f'チャンネル {r.snapshot.get("channel","—")} / 有効な照射帯 {len(r.result.active_spoke_ids)}本'),('最小最大偏差円の半径',f'{m.circle.radius:.4f} {m.unit} / 上限 {limit(r.limits.radius)} / {STATUS[r.judgment.radius]}'),('レーザー点から円中心への偏位',f'{m.laser_distance:.4f} {m.unit} / 上限 {limit(r.limits.laser_distance)} / {STATUS[r.judgment.laser_distance]}'),('偏位の成分',f'X {m.laser_delta.x:+.4f}, Y {m.laser_delta.y:+.4f} {m.unit} （右・下が正）'),('円中心',f'X {m.circle.center.x:.4f}, Y {m.circle.center.y:.4f} {m.unit}'),('記録ID',r.id),('位置づけ','FiStarは施設内QAの補助ツールです。実画像の臨床的精度は未検証です。操作者が確認したうえで施設手順により最終判断してください。評価は保存時の許容値に基づきます。')]
    fields.insert(5,('中心推定方式',METHODS[r.result.center_method]))
    if r.result.center_method=='intersection_centroid':
        m=r.result.selected
        fields=[(label,text) for label,text in fields if label not in ('最小最大偏差円の半径','レーザー点から円中心への偏位','偏位の成分','円中心')]
        fields[7:7]=[
            ('交点重心',f'X {m.center.x:.4f}, Y {m.center.y:.4f} {m.unit}'),
            ('レーザー偏位',f'{m.laser_distance:.4f} {m.unit} / 合否判定なし'),
            ('偏位の成分',f'X {m.laser_delta.x:+.4f}, Y {m.laser_delta.y:+.4f} {m.unit} （右・下が正）'),
            ('交点までの最大距離',f'{m.max_distance:.4f} {m.unit} / 合否判定なし'),
            ('交点',f'使用 {len(m.intersections)}個 / 計算不能ペア {len(m.skipped_pairs)}組'),
            ('警告',f'線間角度1度未満のペア {len(m.warnings)}組。遠方交点により重心が不安定になる可能性があります。' if m.warnings else 'なし')]
        fields=[(label,text.replace('評価は保存時の許容値に基づきます。','交点重心方式では合否判定しません。')) for label,text in fields]
    with atomic_output(path) as temporary:
        writer=QPdfWriter(str(temporary)); writer.setPageSize(QPageSize(QPageSize.A4)); writer.setResolution(144); writer.setTitle('FiStar スターショットQA要約')
        painter=QPainter()
        if not painter.begin(writer): raise OSError('PDFへ書き込めません')
        try:
            width,height=writer.width(),writer.height(); margin=40; area_width=width-2*margin
            layout=None
            for size in (11,10,9,8,7):
                font.setPointSize(size); metrics=QFontMetricsF(font,writer)
                rows=[]; total=100
                for label,text in fields:
                    rect=metrics.boundingRect(QRectF(0,0,area_width,10000),Qt.TextWordWrap,label+'：'+text)
                    row_height=max(rect.height()+18,36); rows.append((label+'：'+text,row_height)); total+=row_height
                if total<=height-2*margin: layout=rows; break
            if layout is None: raise ValueError('名称が長すぎて1ページに収まりません。名称を短くしてください')
            title_font=QFont(font); title_font.setPointSize(18); title_font.setBold(True); painter.setFont(title_font); painter.setPen(QColor('#164451'))
            painter.drawText(QRectF(margin,margin,area_width,55),Qt.AlignLeft|Qt.AlignVCenter,'FiStar  スターショットQA')
            painter.setFont(font); y=margin+90
            for text,row_height in layout:
                painter.setPen(QColor('#233846')); painter.drawText(QRectF(margin,y,area_width,row_height),Qt.TextWordWrap,text)
                y+=row_height
            if not painter.end(): raise OSError('PDFを完了できませんでした')
        finally:
            if painter.isActive(): painter.end()
        if temporary.stat().st_size==0: raise OSError('PDFが空です')
