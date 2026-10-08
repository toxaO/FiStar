from dataclasses import replace,asdict
import math
import unicodedata
import pytest
from pypdf import PdfReader
from fistar.core.models import *
from fistar.pdf_report import select_trend_records,intersection_rows
from fistar.exporting import export_pdf

@pytest.fixture
def record():
    pixels=MetricResult('px',Circle(Point(10,20),2),Point(3,-4),5)
    intersections=(Intersection(('a','b'),Point(11,22),math.sqrt(5)),Intersection(('b','c'),Point(9,18),math.sqrt(5)))
    centroid=CentroidMetric('px',Point(10,20),Point(3,-4),5,intersections,math.sqrt(5),(('a','c'),))
    spokes=[asdict(Spoke(key,Line(1,0,10))) for key in 'abc']
    return Measurement('selected','2026-10-08T12:00:00+09:00','','gantry','image.tif',AnalysisResult(pixels,None,('a','b','c'),centroid,None,center_method='intersection_centroid'),Limits(),Judgment('not_evaluated','not_evaluated'),{'spokes':spokes,'image_path':'/missing.tif','image_sha256':'missing','calibration':None})

def test_latest_15_and_matching_conditions(record):
    records=[replace(record,id=str(i),created_at=f'2026-09-{i+1:02}T12:00:00+09:00') for i in range(20)]
    records+=[replace(record,id='other-device',device='A'),replace(record,id='other-axis',axis='couch'),replace(record,id='other-method',result=replace(record.result,center_method='minimax'))]
    chosen=select_trend_records(record,records)
    assert [r.id for r in chosen]==[str(i) for i in range(5,20)]
    assert select_trend_records(record,[])==()

def test_tie_order_and_units(record):
    mm=replace(record.result.centroid_pixels,unit='mm')
    other=replace(record,id='mm',result=replace(record.result,centroid_physical=mm))
    chosen=select_trend_records(record,[replace(record,id='b'),replace(record,id='a'),other])
    assert [r.id for r in chosen]==['a','b']

def test_intersections_selected_center_and_anisotropic(record):
    rows,skipped=intersection_rows(record)
    assert rows[0]==('1–2',11,22,math.sqrt(5));assert skipped==('1–3',)
    minimized=replace(record,result=replace(record.result,pixels=replace(record.result.pixels,circle=Circle(Point(0,0),2)),center_method='minimax'))
    assert intersection_rows(minimized)[0][0][3]==math.hypot(11,22)
    metric=replace(record.result.centroid_pixels,unit='mm',center=Point(1,4),intersections=(Intersection(('a','b'),Point(1.1,4.4),math.hypot(.1,.4)),))
    physical=replace(record,result=replace(record.result,centroid_physical=metric),snapshot={**record.snapshot,'calibration':{'sx_mm':.1,'sy_mm':.2}})
    row=intersection_rows(physical)[0][0]
    assert row[1:3]==pytest.approx((11,22));assert row[3]==pytest.approx(math.hypot(.1,.4))

def test_missing_image_report_and_pagination(qapp,tmp_path,record):
    before=record.snapshot.copy();path=tmp_path/'report.pdf'
    export_pdf(record,path,'コメントの確認',[record])
    reader=PdfReader(path);assert len(reader.pages)==2
    first=''.join(unicodedata.normalize('NFKC',reader.pages[0].extract_text()).split()).replace('\x01','')
    assert '未入力' in first and 'コメントの確認' in first and '最新1件' in first
    assert '元画像' in first and '5.0000' in first
    assert record.snapshot==before
    assert '交点X' not in reader.pages[1].extract_text() and '交点Y' not in reader.pages[1].extract_text()
    intersections=tuple(Intersection(('a','b'),Point(i,i+1),i) for i in range(70))
    many=replace(record,result=replace(record.result,centroid_pixels=replace(record.result.centroid_pixels,intersections=intersections)))
    export_pdf(many,path,trend_records=[])
    reader=PdfReader(path);assert len(reader.pages)==3
    assert all('帯ペア' in ''.join(unicodedata.normalize('NFKC',p.extract_text()).split()).replace('\x01','') for p in reader.pages[1:])

def test_comment_limit_preserves_output(qapp,tmp_path,record):
    path=tmp_path/'report.pdf';path.write_bytes(b'keep')
    with pytest.raises(ValueError):export_pdf(record,path,'長'*501)
    assert path.read_bytes()==b'keep'


def test_mismatched_image_is_not_rendered(tmp_path,record):
    import numpy as np
    import tifffile
    from fistar.pdf_report import image_session
    path=tmp_path/'other.tif';tifffile.imwrite(path,np.zeros((12,12),dtype=np.uint16))
    altered=replace(record,snapshot={**record.snapshot,'image_path':str(path)})
    session,reason=image_session(altered)
    assert session is None and '一致しません' in reason

def test_period_filter_before_latest_15(tmp_path,record):
    from fistar.storage.repository import connect_database,save_measurement,list_measurements
    connection=connect_database(tmp_path/'records.sqlite')
    for i in range(20):
        r=replace(record,id=str(i),created_at=f'2026-09-{i+1:02}T12:00:00+09:00',snapshot={**record.snapshot,'laser_delta_y_positive':'up'})
        save_measurement(connection,r)
    candidates=list_measurements(connection,device='',axis='gantry',since='2026-09-04T00:00:00+09:00',until='2026-09-08T00:00:00+09:00')
    assert [r.id for r in select_trend_records(record,candidates)]==['3','4','5','6']
    connection.close()

def test_500_character_comment(qapp,tmp_path,record):
    path=tmp_path/'comment.pdf';export_pdf(record,path,'確認'*250,[])
    assert len(PdfReader(path).pages)==2
