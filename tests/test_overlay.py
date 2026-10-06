from dataclasses import replace
from PySide6.QtCore import Qt,QPointF
from PySide6.QtTest import QTest
from fistar.gui.app import MainWindow
from tests.test_session import ready


def window(tmp_path):
    w=MainWindow(database_path=tmp_path/'overlay.sqlite')
    w.session=ready.__wrapped__(); w.panel.session=w.session; w.refresh(); w.show()
    return w


def test_visibility_is_display_only(qapp,tmp_path):
    w=window(tmp_path); qapp.processEvents(); s=w.session
    before=(s.revision,s.dirty,s.result,s.confirmed_steps.copy())
    w.overlay_controls.checks['center'].setChecked(False)
    assert not w.view.visibility['center']
    assert before==(s.revision,s.dirty,s.result,s.confirmed_steps)
    w.overlay_controls.checks['lines'].setChecked(False); w.set_mode('pan')
    QTest.mouseClick(w.view.viewport(),Qt.LeftButton,pos=w.view.mapFromScene(QPointF(2,2)))
    assert before==(s.revision,s.dirty,s.result,s.confirmed_steps)
    s.dirty=False; w.close()


def test_detail_window_reuse_and_independence(qapp,tmp_path):
    w=window(tmp_path); qapp.processEvents(); before=w.view.transform()
    w.open_center_detail(); qapp.processEvents(); d=w.detail_window
    assert d.isVisible() and d.table.rowCount()==3
    assert d.view.read_only and d.view.visibility['intersection_labels']
    assert before==w.view.transform()
    d.controls.checks['center'].setChecked(False)
    assert w.view.visibility['center']
    d.manual_navigation(); d.view.zoom_in(); transform=d.view.transform()
    w.session.set_laser(__import__('fistar.core.models',fromlist=['Point']).Point(3,3)); w.refresh()
    assert d.view.transform()==transform
    w.open_center_detail(); assert w.detail_window is d
    assert 'px' in d.scale_label.text()
    s=w.session; s.dirty=False; w.close()


def test_detail_closes_for_new_image_or_invalid_result(qapp,tmp_path):
    from fistar.core.models import LoadedImage
    import numpy as np
    w=window(tmp_path); qapp.processEvents(); w.open_center_detail(); d=w.detail_window
    w.session.set_image(LoadedImage(tmp_path/'new.tif',np.zeros((10,10)),'new',None)); w.refresh()
    assert not d.isVisible()
    w.session.dirty=False; w.close()


def test_close_when_selected_result_becomes_invalid(qapp,tmp_path):
    w=window(tmp_path); qapp.processEvents(); w.open_center_detail(); d=w.detail_window
    w.session.result=None; w.refresh()
    assert not d.isVisible()
    w.session.dirty=False; w.close()


def test_label_collision_and_duplicate_points(qapp):
    from fistar.gui.overlay import label_layout
    from PySide6.QtCore import QRectF
    points=[(QPointF(250,200),'1–2'),(QPointF(250,200),'1–3'),(QPointF(252,201),'2–3'),(QPointF(253,203),'3–4')]
    layout=label_layout(points,QRectF(0,0,800,500))
    assert len(layout)==3
    assert any('1–2, 1–3'==text for _,text,_ in layout)
    for i,(point,text,rect) in enumerate(layout):
        assert not rect.contains(point)
        assert all(not rect.intersects(other) for _,_,other in layout[i+1:])


def test_all_visibility_and_zoom_are_pure_display(qapp,tmp_path):
    w=window(tmp_path); qapp.processEvents(); s=w.session
    original=(s.result,s.revision,s.confirmed_steps.copy(),s.dirty,w.view.transform())
    for check in w.overlay_controls.checks.values(): check.setChecked(False)
    assert not w.view._overlay
    assert original==(s.result,s.revision,s.confirmed_steps,s.dirty,w.view.transform())
    assert w.view.intersection_data()  # Also available in minimax mode.
    w.open_center_detail(); d=w.detail_window
    d.view.set_mode('laser'); selected=[]; d.view.laser_selected.connect(selected.append)
    QTest.mouseClick(d.view.viewport(),Qt.LeftButton,pos=d.view.mapFromScene(QPointF(2,2)))
    assert not selected
    w.session.dirty=False; w.close()


def test_detail_near_edge_center_and_channel_preserve_position(qapp,tmp_path):
    import numpy as np
    from pathlib import Path
    from fistar.core.models import LoadedImage,Point,Line,Spoke
    from fistar.core.analysis import evaluate_spokes
    w=window(tmp_path); s=w.session
    s.image=LoadedImage(Path('rgb.tif'),np.zeros((10,10,3)),'rgb',None)
    s.spokes=tuple(Spoke(str(i),line) for i,line in enumerate((Line(1,0,0),Line(0,1,0),Line(1,1,0))))
    s.result=evaluate_spokes(s.spokes,Point(2,2),None); w.refresh(); qapp.processEvents(); w.open_center_detail(); qapp.processEvents()
    d=w.detail_window
    center=d.view.mapToScene(d.view.viewport().rect()).boundingRect().center()
    assert d.view.mapToScene(d.view.viewport().rect()).boundingRect().contains(QPointF(0,0))
    assert d.view.mapToScene(d.view.viewport().rect()).boundingRect().contains(QPointF(2,2))
    d.manual_navigation(); transform=d.view.transform(); s.channel='R'; w.refresh()
    assert d.view.transform()==transform
    w.session.dirty=False; w.close()


def test_fixed_markers_require_full_viewport_redraw(qapp,tmp_path):
    from PySide6.QtWidgets import QGraphicsView
    w=window(tmp_path)
    assert w.view.viewportUpdateMode()==QGraphicsView.FullViewportUpdate
    w.open_center_detail()
    assert w.detail_window.scale_bar.width()==96
    w.session.dirty=False; w.close()


def test_auto_fit_contains_far_laser_and_all_labels(qapp):
    from fistar.gui.overlay import auto_fit_detail,label_layout
    from PySide6.QtCore import QRectF
    points=[QPointF(100,100),QPointF(102,101),QPointF(200,180)]
    labels=[(points[0],'1–2'),(points[1],'1–3')]
    fit=auto_fit_detail(points,labels,QRectF(0,0,800,500))
    assert all(QRectF(16,16,768,468).contains(fit.map(point)) for point in points)
    layout=label_layout([(fit.map(p),text) for p,text in labels],QRectF(0,0,800,500),fit.reserved)
    assert len(layout)==2
    assert all(QRectF(0,0,800,500).contains(rect) for _,_,rect in layout)


def test_auto_fit_coincident_and_anisotropic_target(qapp):
    from fistar.gui.overlay import auto_fit_detail
    from PySide6.QtCore import QRectF
    points=[QPointF(32,32)]*3
    labels=[(points[0],'1–2'),(points[0],'1–3')]
    fit=auto_fit_detail(points,labels,QRectF(0,0,900,300))
    assert fit.scale>0 and fit.center==QPointF(32,32)
    assert fit.label_count==1


def test_manual_outlier_position_survives_refresh(qapp,tmp_path):
    from fistar.core.models import Line,Spoke,Point
    from fistar.core.analysis import evaluate_spokes
    w=window(tmp_path);s=w.session
    s.spokes=tuple(Spoke(str(i),line) for i,line in enumerate((Line(1,0,0),Line(0,1,0),Line(1,.001,10))))
    s.result=evaluate_spokes(s.spokes,Point(2,2),None)
    w.refresh();qapp.processEvents();w.open_center_detail();qapp.processEvents()
    d=w.detail_window;d.manual_navigation();d.view.centerOn(QPointF(0,10000))
    before=d.view.mapToScene(d.view.viewport().rect()).boundingRect().center()
    w.refresh();after=d.view.mapToScene(d.view.viewport().rect()).boundingRect().center()
    assert abs(before.x()-after.x())<1 and abs(before.y()-after.y())<1
    s.dirty=False;w.close()


def test_auto_fit_includes_optional_band_label_reservations(qapp):
    from fistar.gui.overlay import auto_fit_detail,label_layout
    from PySide6.QtCore import QRectF
    points=[QPointF(100,100),QPointF(102,101),QPointF(105,109)]
    labels=[(points[0],'1–2'),(points[1],'1–3')]
    bands=[(points[0],'1'),(points[1],'2')]
    frame=QRectF(0,0,800,500)
    fit=auto_fit_detail(points,labels,frame,band_points=bands)
    boxes=label_layout([(fit.map(p),text) for p,text in bands],frame,fit.reserved)
    result=label_layout([(fit.map(p),text) for p,text in labels],frame,(*fit.reserved,*(rect for _,_,rect in boxes)))
    assert len(result)==2


def test_auto_fit_old_record_explains_missing_intersections(qapp,tmp_path):
    w=window(tmp_path);w.session.result=replace(w.session.result,centroid_pixels=None,centroid_physical=None)
    w.refresh();qapp.processEvents();w.open_center_detail();qapp.processEvents()
    assert '交点情報' in w.detail_window.fit_status.text()
    assert '追加計算' in w.detail_window.fit_status.text()
    w.session.dirty=False;w.close()
