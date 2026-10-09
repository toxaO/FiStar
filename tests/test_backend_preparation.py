from pathlib import Path
from dataclasses import replace
import json
import pytest
from fistar.core import backend
from fistar.core.backend import BackendInfo
from fistar.gui.app import MainWindow
from fistar.core.imaging import load_tiff
from fistar.core.models import Point


def test_cache_reuse_and_corrupt_fallback(tmp_path):
    cache,persistent,reused=backend.configure_cache(tmp_path)
    assert persistent and not reused
    (cache/'fontlist-test.json').write_text(json.dumps({'ttflist':[]}))
    assert backend.configure_cache(tmp_path)==(cache,True,True)
    (cache/'fontlist-test.json').write_text('{broken')
    fallback,persistent,reused=backend.configure_cache(tmp_path)
    assert fallback!=cache and not persistent and not reused


def test_unwritable_cache_root(tmp_path):
    root=tmp_path/'not-directory';root.write_text('keep')
    cache,persistent,reused=backend.configure_cache(root)
    assert not persistent and not reused and cache.is_dir()
    assert root.read_text()=='keep'


def test_cache_identity_changes_with_version(monkeypatch):
    before=backend.cache_identity()
    monkeypatch.setattr(backend,'version',lambda name:'changed')
    assert backend.cache_identity()!=before

@pytest.fixture
def window(qapp,tmp_path):
    w=MainWindow(database_path=tmp_path/'isolated.sqlite',cache_path=tmp_path/'cache')
    s=w.session;s.set_image(load_tiff(Path(__file__).parents[1]/'sample/images/starshot-12.tif'))
    h,width=s.image.raw.shape[:2];s.set_laser(Point(width/2,h/2));w.refresh()
    w.backend_state='preparing'
    yield w
    s.dirty=False;w.close()


def test_queued_detection_runs_once(window,monkeypatch):
    calls=[];monkeypatch.setattr(window,'_launch_detection',lambda settings:calls.append(settings))
    settings=window.session.detection_settings;window.detect(settings)
    assert window._pending_detection is not None and not calls
    assert window.panel.laser_button.isEnabled()
    window.view.set_mode('pan');window.view.zoom_in()
    window.backend_prepared(BackendInfo('/tmp/test',True,True,.1),'')
    assert calls==[settings] and window._pending_detection is None


def test_changed_laser_cancels_pending(window,monkeypatch):
    calls=[];monkeypatch.setattr(window,'_launch_detection',lambda settings:calls.append(settings))
    window.detect(window.session.detection_settings)
    laser=window.session.laser;window.session.set_laser(Point(laser.x+1,laser.y))
    window.backend_prepared(BackendInfo('/tmp/test',True,False,.1),'')
    assert not calls and '条件が変わりました' in window.statusBar().currentMessage()


def test_failure_and_retry(window,monkeypatch):
    window.detect(window.session.detection_settings)
    window.backend_prepared(None,'failure')
    assert window.backend_state=='failed' and window._pending_detection is None
    assert not window.backend_retry.isHidden()
    calls=[];monkeypatch.setattr(window.pool,'start',lambda worker:calls.append(worker))
    window.start_backend_preparation()
    assert window.backend_state=='preparing' and len(calls)==1
    window.backend_prepared(BackendInfo('/tmp/test',False,False,.1),'')
    assert window.backend_state=='ready' and '一時キャッシュ' in window.statusBar().currentMessage()


def test_late_preparation_completion_after_close(window):
    window._closing=True
    window.backend_prepared(BackendInfo('/tmp/test',True,False,.1),'')
    assert window.backend_state=='preparing'


@pytest.mark.parametrize('change',['image','settings'])
def test_other_detection_input_changes_cancel_pending(window,monkeypatch,change):
    calls=[];monkeypatch.setattr(window,'_launch_detection',lambda settings:calls.append(settings))
    window.detect(window.session.detection_settings)
    if change=='image':window.session.set_image(window.session.image)
    else:window.session.set_detection_settings(replace(window.session.detection_settings,min_peak_height=.3))
    window.backend_prepared(BackendInfo('/tmp/test',True,False,.1),'')
    assert not calls and window._pending_detection is None


def test_frozen_cache_identity_changes_after_move_and_update(tmp_path,monkeypatch):
    first=tmp_path/'first-app';first.write_bytes(b'first')
    second=tmp_path/'moved-app';second.write_bytes(b'first')
    monkeypatch.setattr(backend.sys,'frozen',True,raising=False)
    monkeypatch.setattr(backend.sys,'executable',str(first))
    original=backend.cache_identity()
    monkeypatch.setattr(backend.sys,'executable',str(second))
    moved=backend.cache_identity();assert moved!=original
    second.write_bytes(b'updated-binary')
    assert backend.cache_identity()!=moved
