import numpy as np

def synthetic_starshot(angles_deg, *, shape=(512,512),width_px=10,seed=0):
    y,x = np.indices(shape)
    x=x-shape[1]/2; y=y-shape[0]/2
    image=np.full(shape,240.,dtype=float)
    for angle in angles_deg:
        a=np.deg2rad(angle)
        image[np.abs(-np.sin(a)*x+np.cos(a)*y)<=width_px/2]=40
    return image
