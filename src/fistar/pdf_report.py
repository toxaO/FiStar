"""保存記録から作る、解析状態を変更しないPDFレポート。"""
import math
from datetime import datetime
from types import SimpleNamespace
from PySide6.QtCore import Qt,QRectF,QPointF,QMarginsF
from PySide6.QtGui import QPainter,QColor,QFont,QFontMetricsF,QImage,QPdfWriter,QPageSize
from PySide6.QtWidgets import QFrame
from fistar.core.models import Point,Line,Spoke,Calibration,DetectionSettings
from fistar.core.imaging import load_tiff
from fistar.gui.image_view import ImageView
from fistar.gui.overlay import DEFAULTS,DETAIL_DEFAULTS,auto_fit_detail


def select_trend_records(record,records):
    unit=record.result.selected.unit
    candidates=[r for r in records if (r.device,r.axis,r.result.center_method)==(record.device,record.axis,record.result.center_method) and r.result.selected is not None and r.result.selected.unit==unit]
    return tuple(sorted(candidates,key=lambda r:(datetime.fromisoformat(r.created_at).timestamp(),r.id))[-15:])


def intersection_rows(record):
    result=record.result;selected=result.selected;physical=selected.unit=='mm'
    metric=result.centroid_physical if physical else result.centroid_pixels
    if metric is None:return (),()
    calibration=record.snapshot.get('calibration')
    sx=calibration['sx_mm'] if physical else 1;sy=calibration['sy_mm'] if physical else 1
    center=selected.center if result.center_method=='intersection_centroid' else selected.circle.center
    numbers={s['id']:str(i+1) for i,s in enumerate(record.snapshot.get('spokes',())) if 'id' in s}
    def pair(ids):return '–'.join(numbers.get(key,key) for key in ids)
    rows=tuple((pair(p.spoke_ids),p.point.x/sx,p.point.y/sy,math.hypot(p.point.x-center.x,p.point.y-center.y)) for p in metric.intersections)
    return rows,tuple(pair(ids) for ids in metric.skipped_pairs)


def image_session(record,data_dir=None):
    data=record.snapshot
    try:
        if data.get('reference_image'):
            if data_dir is None:raise ValueError('参考画像のデータフォルダが指定されていません')
            from fistar.storage.portable import load_reference
            image=load_reference(record,data_dir)
        else:
            if not data.get('image_path'):raise ValueError('参考画像がありません')
            image=load_tiff(data['image_path'])
            if image.sha256!=data.get('image_sha256'):raise ValueError('元画像が保存時の画像と一致しません')
    except Exception as error:return None,'元画像を表示できません：'+str(error)
    calibration=data.get('calibration');c=Calibration(calibration['sx_mm'],calibration['sy_mm'],calibration['source']) if calibration else None
    spokes=tuple(Spoke(s['id'],Line(**s['line']),tuple(Point(**p) for p in s.get('support',())),s.get('origin','auto'),s.get('excluded',False)) for s in data.get('spokes',()))
    settings=data.get('detection_settings') or {}
    settings=DetectionSettings(**settings) if 'radius_ratio' in settings else DetectionSettings()
    session=SimpleNamespace(image=image,calibration=c,spokes=spokes,laser=Point(**data['laser']) if data.get('laser') else None,result=record.result,center_method=record.result.center_method,detection=None,detection_settings=settings,axis_definition=data.get('axis_definition',{}))
    return session,''


def render_image(session,detail=False):
    # Fixed output dimensions make label layout independent of desktop window size.
    view=ImageView();view.read_only=True;view.setFrameShape(QFrame.NoFrame)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.resize(400 if detail else 355,400 if detail else 355);view.visibility=dict(DETAIL_DEFAULTS if detail else DEFAULTS)
    view.visibility.update(search_circle=False,detection_points=False,offset=False,intersection_labels=detail,intersections=detail,band_labels=not detail,evaluation_circle=not detail and session.center_method=='minimax')
    view.set_session(session);view.ensurePolished()
    # Hidden widgets still require their final viewport geometry before fitting.
    view.show();view.hide()
    scale=None
    if detail:
        center=view.selected_center();labels=[(p,text) for p,text,_ in view.intersection_data()]
        points=[center]+([QPointF(session.laser.x,session.laser.y)] if session.laser else [])+[p for p,_ in labels]
        fit=auto_fit_detail(points,labels,view.viewport().rect())
        scale=fit.scale;side=view.viewport().width()/scale
        view.setSceneRect(QRectF(fit.center.x()-side,fit.center.y()-side,side*2,side*2))
        view.resetTransform();view.scale(scale,scale);view.centerOn(fit.center)
    else:view.reset_view()
    image=QImage(view.viewport().size()*3,QImage.Format_RGB32);image.setDevicePixelRatio(3);image.fill(QColor('#111d28'))
    view.viewport().render(image);view.close();view.deleteLater()
    return image,scale


def render_trend(record,records,metric,height=250):
    from fistar.gui.records_panel import TrendPlot
    widget=TrendPlot();widget.setMinimumHeight(0);widget.resize(760,int(height));widget.ensurePolished()
    widget.records=tuple(reversed(records));widget.center_method=record.result.center_method
    widget.unit=record.result.selected.unit;widget.metric_name=metric;widget.enabled=True;widget.highlight_id=record.id
    image=QImage(widget.size()*3,QImage.Format_RGB32);image.setDevicePixelRatio(3);image.fill(Qt.white);widget.render(image);widget.deleteLater()
    return image


def write_report(record,path,font,comment,trend_records,period_label,data_dir=None):
    from fistar.gui.analysis_panel import AXES,METHODS
    r=record;m=r.result.selected
    if m is None:raise ValueError('選択方式の保存結果がありません')
    if len(comment)>500:raise ValueError('コメントは500文字以内で入力してください')
    records=select_trend_records(r,trend_records);rows,skipped=intersection_rows(r)
    session,image_error=image_session(r,data_dir)
    full=detail=None;scale=None
    if session:full,_=render_image(session);detail,scale=render_image(session,True)
    centroid=r.result.center_method=='intersection_centroid';spread=m.max_distance if centroid else m.circle.radius
    spread_name='最大距離' if centroid else '最大半径'
    calibration=r.snapshot.get('calibration');axis=r.snapshot.get('axis_definition',{})
    warnings=(r.result.centroid_physical or r.result.centroid_pixels)
    numbers={s['id']:str(i+1) for i,s in enumerate(r.snapshot.get('spokes',())) if 'id' in s}
    warning_text='／'.join(warnings.warnings) if warnings else r.result.centroid_error
    for key,value in numbers.items():warning_text=warning_text.replace(key,value)
    fields=[('測定日時',datetime.fromisoformat(r.created_at).astimezone().strftime('%Y/%m/%d %H:%M:%S')),('装置名',r.device or '未入力'),('回転軸',axis.get('name',AXES.get(r.axis,r.axis))),('画像名',r.image_name),('中心推定方式',METHODS[r.result.center_method]),('中心偏位（レーザー中心基準）',f'{m.laser_distance:.4f} {m.unit}'),('偏位X・Y',f'X {m.laser_delta.x:+.4f} / Y {m.laser_delta.y:+.4f} {m.unit}'),(spread_name,f'{spread:.4f} {m.unit}'),('解像度',f'X {calibration["sx_mm"]:.4f} / Y {calibration["sy_mm"]:.4f} mm/px' if calibration else '未校正（px）'),('使用帯数',str(len(r.result.active_spoke_ids))),('交点',f'{len(rows)}個 / 計算不能 {len(skipped)}組' if warnings else '交点情報なし')]
    table_rows=[(pair,f'{distance:.4f}') for pair,x,y,distance in rows]
    table_rows.extend((pair,'交点未定義') for pair in skipped)
    # 2nd page has the 100mm image; following pages are table-only.
    chunks=[table_rows[:57]];remaining=table_rows[57:]
    while remaining:chunks.append(remaining[:120]);remaining=remaining[120:]
    page_count=1+len(chunks)
    writer=QPdfWriter(str(path));writer.setPageSize(QPageSize(QPageSize.A4));writer.setPageMargins(QMarginsF(0,0,0,0));writer.setResolution(144);writer.setTitle('FiStar スターショットQAレポート')
    painter=QPainter()
    if not painter.begin(writer):raise OSError('PDFへ書き込めません')
    def setfont(size=13,bold=False):
        f=QFont(font);f.setPixelSize(size);f.setBold(bold);painter.setFont(f)
    def text(x,y,w,h,value,size=13,bold=False):
        setfont(size,bold);painter.setPen(QColor('#233846'));painter.drawText(QRectF(x,y,w,h),Qt.TextWordWrap,value)
    def height(value,w,size=13):
        setfont(size);return QFontMetricsF(painter.font()).boundingRect(QRectF(0,0,w,10000),Qt.TextWordWrap,value).height()+6
    def start_page(number,title):
        painter.save();painter.scale(writer.width()/840,writer.height()/1188)
        text(40,28,760,36,title,23,True)
        painter.setPen(QColor('#0794a3'));painter.drawLine(40,70,800,70)
        text(40,1136,660,20,'記録ID：'+r.id,11);text(730,1136,70,20,f'{number} / {page_count}',11)
    try:
        start_page(1,'FiStar  スターショットQAレポート')
        size=13
        def field_height(label,value):return max(22 if size<12 else 26,height(label,118,size)-2,height(value,238,size)-2)
        while size>8 and sum(field_height(label,value) for label,value in fields)>407:size-=1
        if sum(field_height(label,value) for label,value in fields)>407:raise ValueError('基本情報がページに収まりません。装置名・軸名・画像名を短くしてください')
        y=88
        for label,value in fields:
            h=field_height(label,value)
            painter.fillRect(QRectF(40,y,130,h),QColor('#e5edf2'))
            text(46,y+2,118,h-2,label,size,True);text(176,y+2,238,h-2,value,size)
            painter.setPen(QColor('#dce5eb'));painter.drawRect(QRectF(40,y,380,h));painter.drawLine(QPointF(170,y),QPointF(170,y+h));y+=h
        text(445,88,355,25,'全体画像',15,True)
        if full:painter.drawImage(QRectF(445,118,355,355),full)
        else:text(445,118,355,355,image_error)
        if not axis:text(445,477,355,28,'方向ラベル：保存情報なし',11)
        text(40,495,760,22,'偏位：X右正・Y上正。座標：X右向き・Y下向き。',12)
        extra=('警告：'+warning_text+'\n' if warning_text else '')+('コメント：'+comment if comment else '')
        extra_height=0
        if extra:
            size=13
            while size>10 and height(extra,760,size)>125:size-=1
            if height(extra,760,size)>125:raise ValueError('警告・コメントがレポートに収まりません。コメントを短くしてください')
            extra_height=height(extra,760,size)
            text(40,522,760,extra_height,extra,size)
        period=period_label or '全期間'
        note=f'トレンド：{period} / 最新{len(records)}件（最大15件）'
        if records:note+=' / '+datetime.fromisoformat(records[0].created_at).astimezone().strftime('%Y/%m/%d')+'–'+datetime.fromisoformat(records[-1].created_at).astimezone().strftime('%Y/%m/%d')
        trend_y=max(530,522+extra_height+10)
        text(40,trend_y,760,25,note,12)
        if not any(item.id==r.id for item in records):text(40,trend_y+28,760,24,'選択記録はトレンド対象外です（期間・件数・単位の条件）。',11)
        else:text(40,trend_y+28,760,24,'輪郭で囲んだ点：選択記録',11)
        graph_y=trend_y+57;graph_height=int((1090-graph_y-12)/2)
        painter.drawImage(QRectF(40,graph_y,760,graph_height),render_trend(r,records,'laser_distance',graph_height))
        painter.drawImage(QRectF(40,graph_y+graph_height+12,760,graph_height),render_trend(r,records,'radius',graph_height))
        text(40,1100,760,24,'施設内QAの補助用。実画像の臨床的精度は未検証です。',11)
        painter.restore()
        for page,chunk in enumerate(chunks,2):
            if not writer.newPage():raise OSError('PDFの改ページに失敗しました')
            start_page(page,'中心付近の拡大・交点一覧' if page==2 else '交点一覧（続き）')
            y=96
            if page==2:
                if detail:painter.drawImage(QRectF(220,96,400,400),detail)
                else:text(220,96,400,400,image_error)
                text(40,507,760,24,'水色：レーザー点 / 赤（最小円は紫）：推定中心 / 白：交点',12)
                if scale:
                    pixels=80/scale
                    painter.setPen(QColor('#233846'));painter.drawLine(40,544,120,544);painter.drawLine(40,540,40,548);painter.drawLine(120,540,120,548)
                    value=f'原画像 {pixels:.4f} px'
                    if calibration:value+=f' / X {pixels*calibration["sx_mm"]:.4f}, Y {pixels*calibration["sy_mm"]:.4f} mm'
                    text(132,535,668,24,value,12)
                text(40,566,760,26,f'交点の距離：選択方式の推定中心基準 [{m.unit}]',12)
                y=602
            # Read down each column, then continue with the next column.
            row_count=(len(chunk)+2)//3
            for column in range(3):
                x=40+column*260
                painter.fillRect(QRectF(x,y,240,26),QColor('#e5edf2'))
                text(x+6,y+5,90,21,'帯ペア',12,True)
                text(x+102,y+5,132,21,f'中心からの距離 [{m.unit}]',12,True)
                for index,(pair,distance) in enumerate(chunk[column*row_count:(column+1)*row_count]):
                    line_y=y+26+index*24
                    text(x+6,line_y+4,90,20,pair,13)
                    text(x+102,line_y+4,132,20,distance,13)
                    painter.setPen(QColor('#dce5eb'));painter.drawLine(x,int(line_y+24),x+240,int(line_y+24))
            if not table_rows:text(45,y+34,750,30,'交点情報なし',13)
            painter.restore()
        if not painter.end():raise OSError('PDFを完了できませんでした')
    finally:
        if painter.isActive():painter.end()
