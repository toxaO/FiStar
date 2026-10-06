from pathlib import Path
import numpy as np
import pytest
import tifffile
from fistar.core.models import Point
from fistar.core.imaging import load_tiff, analysis_channel, manual_calibration, display_image

def test_rgb16_preserved(tmp_path):
    raw = np.array([[[1000, 2000, 3000], [65535, 0, 0]]], dtype=np.uint16)
    path = tmp_path / 'rgb.tif'
    tifffile.imwrite(path, raw, photometric='rgb')
    image = load_tiff(path)
    assert image.raw.dtype == np.uint16
    np.testing.assert_array_equal(image.raw, raw)
    assert analysis_channel(image, 'R')[0, 0] == 1000
    assert analysis_channel(image, 'G')[0, 0] == 2000
    assert analysis_channel(image, 'B')[0, 0] == 3000
    assert analysis_channel(image, 'luminance')[0, 0] == pytest.approx(1815)
    display_image(analysis_channel(image, 'R'), 0, 65535)
    np.testing.assert_array_equal(image.raw, raw)

@pytest.mark.parametrize('unit,res,want', [('INCH',(100,200),(.254,.127)), ('CENTIMETER',(100,200),(.1,.05))])
def test_resolution_axes(tmp_path, unit, res, want):
    p = tmp_path / 'scale.tif'
    tifffile.imwrite(p, np.zeros((10,10),np.uint16), resolution=res, resolutionunit=unit)
    c = load_tiff(p).tagged_calibration
    assert (c.sx_mm,c.sy_mm) == pytest.approx(want)

def test_no_unit_and_multipage(tmp_path):
    p = tmp_path / 'no.tif'
    tifffile.imwrite(p, np.zeros((10,10)), resolution=(100,100), resolutionunit='NONE')
    assert load_tiff(p).tagged_calibration is None
    with tifffile.TiffWriter(p) as f:
        f.write(np.zeros((10,10)))
        f.write(np.zeros((10,10)))
    with pytest.raises(ValueError): load_tiff(p)

def test_manual_scale():
    c = manual_calibration(Point(0,0), Point(10,0), 5)
    assert c.sx_mm == c.sy_mm == .5

@pytest.mark.parametrize('end,length', [(Point(0,0),5),(Point(1,0),0),(Point(1,0),-1),(Point(1,0),float('nan'))])
def test_invalid_manual(end,length):
    with pytest.raises(ValueError): manual_calibration(Point(0,0),end,length)

def test_miniswhite_raw_kept(tmp_path):
    p=tmp_path/'white.tif'; raw=np.array([[0,65535],[30000,1000]],np.uint16)
    tifffile.imwrite(p,raw,photometric='miniswhite')
    image=load_tiff(p)
    np.testing.assert_array_equal(image.raw,raw)
    assert image.photometric=='MINISWHITE'
