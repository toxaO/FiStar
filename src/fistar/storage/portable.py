"""Portable records and display-only JPEG references."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import numpy as np
from PySide6.QtGui import QImage
from fistar.core.imaging import analysis_channel,display_image,load_tiff
from fistar.core.models import LoadedImage
from .repository import save_measurement,list_measurements


def portable_data_dir():
    if getattr(sys,'frozen',False):
        executable=Path(sys.executable).resolve()
        bundle=next((p for p in executable.parents if p.suffix=='.app'),None)
        root=bundle.parent if bundle else executable.parent
    else:root=Path(__file__).resolve().parents[3]
    return root/'data'


def database_dir(connection):
    return Path(connection.execute('PRAGMA database_list').fetchone()[2]).parent


def reference_path(record,data_dir):
    reference=record.snapshot.get('reference_image')
    if not reference:return None
    root=(Path(data_dir)/'images').resolve()
    path=(Path(data_dir)/reference['path']).resolve()
    if path.parent!=root or path.suffix.lower() not in ('.jpg','.jpeg'):raise ValueError('参考画像の保存先が不正です')
    return path


def with_reference(record,image,data_dir):
    folder=Path(data_dir)/'images';folder.mkdir(parents=True,exist_ok=True)
    name=record.id if re.fullmatch(r'[A-Za-z0-9_-]+',record.id) else hashlib.sha256(record.id.encode()).hexdigest()
    destination=folder/(name+'.jpg')
    values=analysis_channel(image);low,high=np.percentile(values,[.5,99.5]);pixels=display_image(values,float(low),float(high) if high>low else float(low)+1)
    if image.photometric=='MINISWHITE':pixels=255-pixels
    h,w=pixels.shape;picture=QImage(pixels.data,w,h,pixels.strides[0],QImage.Format_Grayscale8).copy()
    with tempfile.NamedTemporaryFile(dir=folder,suffix='.jpg',delete=False) as stream:temporary=Path(stream.name)
    try:
        if not picture.save(str(temporary),'JPEG',95):raise OSError('参考JPEGを保存できません')
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    snapshot={**record.snapshot,'image_path':None,'reference_image':{'path':'images/'+destination.name,'width':w,'height':h,'purpose':'display-only'}}
    return replace(record,snapshot=snapshot)


def save_with_reference(connection,record,image):
    if connection.execute('SELECT 1 FROM measurements_v1 WHERE id=?',(record.id,)).fetchone():raise ValueError('同じ記録IDが保存されています')
    root=database_dir(connection);saved=with_reference(record,image,root)
    try:save_measurement(connection,saved)
    except Exception:
        reference_path(saved,root).unlink(missing_ok=True);raise
    return saved


def load_reference(record,data_dir):
    path=reference_path(record,data_dir)
    if path is None:raise ValueError('参考JPEGがありません')
    picture=QImage(str(path))
    if picture.isNull():raise ValueError('参考JPEGを読み込めません')
    picture=picture.convertToFormat(QImage.Format_Grayscale8)
    pixels=np.frombuffer(picture.bits(),dtype=np.uint8).reshape(picture.height(),picture.bytesPerLine())[:,:picture.width()].copy()
    reference=record.snapshot['reference_image']
    if pixels.shape!=(reference['height'],reference['width']):raise ValueError('参考JPEGの寸法が保存時と異なります')
    pixels.flags.writeable=False
    return LoadedImage(path,pixels,hashlib.sha256(path.read_bytes()).hexdigest(),None)


def delete_records(connection,records):
    root=database_dir(connection)
    with connection:
        connection.executemany('DELETE FROM measurements_v1 WHERE id=?',[(r.id,) for r in records])
    kept={r.snapshot.get('reference_image',{}).get('path') for r in list_measurements(connection)}
    errors=[]
    for record in records:
        reference=record.snapshot.get('reference_image')
        if not reference or reference['path'] in kept:continue
        try:reference_path(record,root).unlink(missing_ok=True)
        except (OSError,ValueError) as exc:errors.append(str(exc))
    return errors


def import_legacy(connection,source):
    """Explicit import only. Never modifies the original DB or TIFFs."""
    source=Path(source).resolve();root=database_dir(connection)
    if source==root/'fistar-v1.sqlite':raise ValueError('現在の保存先と同じです')
    legacy=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    try:records=list_measurements(legacy)
    finally:legacy.close()
    existing={r.id for r in list_measurements(connection)};added=missing=0
    for record in records:
        if record.id in existing:continue
        saved=record
        try:
            if record.snapshot.get('reference_image'):image=load_reference(record,source.parent)
            else:
                image=load_tiff(record.snapshot.get('image_path') or '')
                if image.sha256!=record.snapshot.get('image_sha256'):raise ValueError('元画像不一致')
        except Exception:
            missing+=1;saved=replace(record,snapshot={**record.snapshot,'image_path':None,'reference_image':None})
        else:saved=with_reference(record,image,root)
        save_measurement(connection,saved);added+=1
    return added,missing
