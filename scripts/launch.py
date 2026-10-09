"""Frozen application entry point and isolated build verification."""
import sys

def smoke_test(image_path,output_path):
    import json
    import os
    import tempfile
    import time
    started=time.perf_counter()
    from pathlib import Path
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from fistar.gui.app import MainWindow
    from fistar.core.imaging import load_tiff,analysis_channel
    from fistar.core.detection import detect_spokes
    from fistar.core.models import Point
    from fistar.exporting import export_pdf
    from fistar.storage.portable import save_with_reference
    app=QApplication([]);app.setApplicationName('FiStar');app.setOrganizationName('FiStar')
    output=Path(output_path);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fistar-build-check-') as temporary:
        window=MainWindow(database_path=Path(temporary)/'test.sqlite',cache_path=output/'cache')
        window.show();app.processEvents()
        startup_seconds=time.perf_counter()-started
        (output/'startup.json').write_text(json.dumps({'pid':os.getpid(),'seconds':startup_seconds,'backend_loaded': 'pylinac' in sys.modules},indent=2))
        deadline=time.monotonic()+120
        while window.backend_state not in ('ready','failed'):
            app.processEvents();time.sleep(.01)
            if time.monotonic()>deadline:raise RuntimeError('Backend preparation timed out')
        if window.backend_state!='ready':raise RuntimeError(window.statusBar().currentMessage())
        preparation_seconds=window.backend_info.seconds
        cache_reused=window.backend_info.reused
        session=window.session;session.set_image(load_tiff(Path(image_path)))
        h,w=session.image.raw.shape[:2];session.set_laser(Point(w/2,h/2))
        detection_started=time.perf_counter()
        session.set_detection(detect_spokes(analysis_channel(session.image),session.laser,session.detection_settings))
        detection_seconds=time.perf_counter()-detection_started
        window.refresh();window.show();app.processEvents()
        assert not window.windowIcon().isNull(),'Application icon missing'
        session.confirm_step('result');record=save_with_reference(window.connection,session.measurement(),session.image)
        export_pdf(record,output/'report.pdf',trend_records=[record],data_dir=Path(temporary))
        window.grab().save(str(output/'window.png'))
        report={'ok':True,'spokes':len(session.spokes),'method':session.center_method,'pylinac':session.detection.pylinac_version,'frozen':getattr(sys,'frozen',False),'startup_seconds':startup_seconds,'preparation_seconds':preparation_seconds,'detection_seconds':detection_seconds,'cache_reused':cache_reused,'cache_path':window.backend_info.cache_path}
        session.dirty=False;window.close()
        (output/'result.json').write_text(json.dumps(report,indent=2))
    return 0

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--smoke-test':
        raise SystemExit(smoke_test(sys.argv[2],sys.argv[3]))
    from fistar.gui.app import main
    raise SystemExit(main())
