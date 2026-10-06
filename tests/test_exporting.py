import csv
from dataclasses import replace
import pytest
from pypdf import PdfReader
from tests.test_repository import measurement
from fistar.exporting import export_csv,export_pdf

def test_csv_header_and_quoted_japanese(tmp_path,measurement):
    p=tmp_path/'records.csv'; export_csv((),p)
    assert '装置名' in p.read_text().splitlines()[0]
    export_csv((replace(measurement,device='装置,改行\n日本語'),),p)
    with p.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    assert rows[0]['装置名']=='装置,改行\n日本語'
    assert float(rows[0]['半径'])==.123456789

def test_one_page_japanese_pdf(qapp,tmp_path,measurement):
    p=tmp_path/'report.pdf'
    export_pdf(replace(measurement,device='治療装置'+('長い名称'*25),image_name='画像'+('長いファイル名'*30)+'.tif'),p)
    reader=PdfReader(p)
    assert len(reader.pages)==1
    text=reader.pages[0].extract_text()
    assert 'FiStar' in text and '0.1235' in text
    assert '治療装置' in text.replace(' ','')

def test_export_failure_preserves_target(tmp_path,measurement):
    p=tmp_path/'existing.csv'; p.write_text('keep')
    with pytest.raises(Exception): export_csv((None,),p)
    assert p.read_text()=='keep'
    assert list(tmp_path.iterdir())==[p]
