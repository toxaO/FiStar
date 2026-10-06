import numpy as np
import pytest
from tests.fixtures.synthetic_starshot import synthetic_starshot
from fistar.core.models import Point, DetectionSettings
from fistar.core.detection import detect_spokes

@pytest.mark.parametrize('angles', [(0,25,50,90,120,150),(0,25,90,120,150)])
@pytest.mark.parametrize('bright,noise', [(False,0),(True,0),(False,3)])
def test_bands_not_arms(angles,bright,noise):
    image=synthetic_starshot(angles)
    image[250:262,250:262]=0
    image[10:40,10:120]=0
    if noise: image+=np.random.default_rng(4).normal(0,noise,image.shape)
    if bright: image=255-image
    result=detect_spokes(image,Point(256,256),DetectionSettings(.6,.25,polarity='bright' if bright else 'dark'))
    assert len(result.spokes)==len(angles)
    for s in result.spokes:
        assert abs(s.line.nx*256+s.line.ny*256-s.line.offset)<1
    for angle in angles:
        direction=np.array([np.cos(np.deg2rad(angle)),np.sin(np.deg2rad(angle))])
        line=min((s.line for s in result.spokes),key=lambda l:abs(np.array([l.nx,l.ny])@direction))
        assert abs(np.array([line.nx,line.ny])@direction)<np.sin(np.deg2rad(1))
        point=np.array([256,256])+120*direction
        assert abs(line.nx*point[0]+line.ny*point[1]-line.offset)<1

@pytest.mark.parametrize('settings', [dict(radius_ratio=0),dict(radius_ratio=1),dict(min_peak_height=0),dict(min_peak_height=float('nan')),dict(polarity='bad')])
def test_invalid_detection_conditions(settings):
    with pytest.raises(ValueError): DetectionSettings(**settings)

def test_matches_pylinac_fwhm_and_pairing():
    from pylinac.core.image import ArrayImage
    from pylinac.core.geometry import Point as PylinacPoint
    from pylinac.starshot import StarProfile
    values=synthetic_starshot((0,25,50,90,120,150))
    before=values.copy(); hub=Point(271,245); settings=DetectionSettings()
    expected=StarProfile(ArrayImage(values.max()-values),PylinacPoint(hub.x,hub.y),settings.radius_ratio,settings.min_peak_height,fwhm=True)
    result=detect_spokes(values,hub,settings)
    points=sorted(expected.peaks,key=lambda p:np.arctan2(p.y-hub.y,p.x-hub.x)%(2*np.pi))
    assert result.method=='pylinac-fwhm' and result.pylinac_version=='3.48.0'
    assert [(p.x,p.y) for p in result.points]==pytest.approx([(p.x,p.y) for p in points])
    assert result.radius_px==pytest.approx(241*.85)
    assert result.search_center==hub
    for i,spoke in enumerate(result.spokes):
        assert spoke.support==(result.points[i],result.points[i+len(result.spokes)])
        for point in spoke.support:
            assert abs(spoke.line.nx*point.x+spoke.line.ny*point.y-spoke.line.offset)<1e-8
    np.testing.assert_array_equal(values,before)

@pytest.mark.parametrize('angles', [(0,90),(0,60)])
def test_fewer_than_six_points_rejected(angles):
    with pytest.raises(ValueError,match='6点'):
        detect_spokes(synthetic_starshot(angles),Point(256,256),DetectionSettings())

def test_odd_points_rejected():
    image=synthetic_starshot((0,60,120))
    image[251:262,256:]=240  # Remove one arm, keeping the opposing arm.
    with pytest.raises(ValueError,match='奇数'):
        detect_spokes(image,Point(256,256),DetectionSettings())

@pytest.mark.parametrize('image,hub', [(np.ones((50,50)),Point(25,25)),(np.full((50,50),np.nan),Point(25,25)),(np.ones((50,50)),Point(0,25))])
def test_invalid_image_or_circle(image,hub):
    with pytest.raises(ValueError): detect_spokes(image,hub,DetectionSettings())
