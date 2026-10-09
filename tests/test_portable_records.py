from dataclasses import replace
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import pytest
from pypdf import PdfReader
from PySide6.QtWidgets import QAbstractItemView,QMessageBox
from fistar.storage.repository import connect_database,list_measurements,save_measurement
from fistar.storage.portable import save_with_reference,load_reference,delete_records,import_legacy,reference_path
from fistar.pdf_report import image_session
from fistar.exporting import export_pdf
from tests.test_session import ready


def test_reference_portability_and_pdf(qapp,tmp_path):
    s=ready.__wrapped__();r=s.measurement();root=tmp_path/'data';c=connect_database(root/'fistar-v1.sqlite')
    r=save_with_reference(c,r,s.image)
    assert r.snapshot['image_path'] is None and r.snapshot['reference_image']['path'].startswith('images/')
    assert load_reference(r,root).raw.shape==s.image.raw.shape
    c.close();moved=tmp_path/'moved';shutil.copytree(root,moved)
    image,error=image_session(r,moved);assert image is not None and not error
    export_pdf(r,tmp_path/'reference.pdf',data_dir=moved)
    assert len(PdfReader(tmp_path/'reference.pdf').pages)==2


def test_bulk_delete_removes_only_selected_jpegs(qapp,tmp_path):
    s=ready.__wrapped__();c=connect_database(tmp_path/'data/fistar-v1.sqlite')
    records=[save_with_reference(c,replace(s.measurement(),id=str(i)),s.image) for i in range(3)]
    paths=[reference_path(r,tmp_path/'data') for r in records]
    assert not delete_records(c,records[:2])
    assert [r.id for r in list_measurements(c)]==['2']
    assert not paths[0].exists() and not paths[1].exists() and paths[2].exists();c.close()


def test_legacy_import_preserves_original_and_missing_image(qapp,tmp_path):
    s=ready.__wrapped__();source=tmp_path/'old.sqlite';c=connect_database(source)
    record=replace(s.measurement(),snapshot={**s.snapshot(),'image_path':'/missing.tif'})
    save_measurement(c,record);c.close();before=hashlib.sha256(source.read_bytes()).hexdigest()
    target=connect_database(tmp_path/'data/fistar-v1.sqlite')
    assert import_legacy(target,source)==(1,1)
    assert import_legacy(target,source)==(0,0)
    assert list_measurements(target)[0].snapshot['image_path'] is None
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before;target.close()


def test_reference_path_cannot_escape_data(tmp_path):
    s=ready.__wrapped__();r=replace(s.measurement(),snapshot={'reference_image':{'path':'../outside.jpg'}})
    with pytest.raises(ValueError):reference_path(r,tmp_path)


def test_multi_selection_deletion_confirmation(qapp,tmp_path,monkeypatch):
    from fistar.gui.records_panel import RecordsPanel
    s=ready.__wrapped__();c=connect_database(tmp_path/'data/fistar-v1.sqlite')
    for i in range(3):save_with_reference(c,replace(s.measurement(),id=str(i)),s.image)
    panel=RecordsPanel(c);panel.table.selectRow(0)
    selection=panel.table.selectionModel()
    from PySide6.QtCore import QItemSelectionModel
    selection.select(panel.table.model().index(1,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
    assert len(panel.selected_records())==2
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.No);panel.delete();assert len(list_measurements(c))==3
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.Yes);panel.delete();assert len(list_measurements(c))==1
    c.close()


def test_legacy_tiff_to_jpeg(qapp,tmp_path):
    from fistar.core.imaging import load_tiff
    source_image=Path(__file__).parents[1]/'sample/images/starshot-18.tif'
    loaded=load_tiff(source_image);s=ready.__wrapped__()
    record=replace(s.measurement(),snapshot={**s.snapshot(),'image_path':str(source_image),'image_sha256':loaded.sha256})
    source=tmp_path/'old.sqlite';old=connect_database(source);save_measurement(old,record);old.close()
    target=connect_database(tmp_path/'data/fistar-v1.sqlite')
    assert import_legacy(target,source)==(1,0)
    saved=list_measurements(target)[0];assert load_reference(saved,tmp_path/'data').raw.shape==loaded.raw.shape[:2]
    target.close()


def test_duplicate_save_keeps_existing_reference(qapp,tmp_path):
    s=ready.__wrapped__();c=connect_database(tmp_path/'data/fistar-v1.sqlite')
    record=save_with_reference(c,s.measurement(),s.image)
    path=reference_path(record,tmp_path/'data');before=path.read_bytes()
    with pytest.raises(ValueError):save_with_reference(c,record,s.image)
    assert path.read_bytes()==before;c.close()


def test_reference_view_is_read_only(qapp,tmp_path):
    from fistar.gui.records_panel import RecordsPanel
    s=ready.__wrapped__();c=connect_database(tmp_path/'data/fistar-v1.sqlite')
    record=save_with_reference(c,s.measurement(),s.image)
    panel=RecordsPanel(c);panel.table.selectRow(0);panel.show_reference();qapp.processEvents()
    assert panel.reference_window.view.read_only
    assert panel.reference_window.view.session.result==record.result
    assert not hasattr(panel,'reopen_requested')
    panel.reference_window.close();panel.close();c.close()
