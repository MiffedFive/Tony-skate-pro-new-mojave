"""Inspect forward-kinematic consequences of candidate local bone rotations."""
from kf_inspect import N, ROOT, vec
import math

def qmul(a, b):
    q = N.Quaternion()
    q.w = a.w*b.w - a.x*b.x - a.y*b.y - a.z*b.z
    q.x = a.w*b.x + a.x*b.w + a.y*b.z - a.z*b.y
    q.y = a.w*b.y - a.x*b.z + a.y*b.w + a.z*b.x
    q.z = a.w*b.z + a.x*b.y - a.y*b.x + a.z*b.w
    return q

def qmatrix(q):
    w,x,y,z = q.w,q.x,q.y,q.z
    m = N.Matrix33()
    m.m_11, m.m_12, m.m_13 = 1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)
    m.m_21, m.m_22, m.m_23 = 2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x)
    m.m_31, m.m_32, m.m_33 = 2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)
    return m

def probe(arm, thigh, calf):
    data = N.Data()
    with (ROOT / 'MO2/mods/NV Compatibility Skeleton/Meshes/Characters/_Male/Skeleton.nif').open('rb') as f:
        data.read(f)
    root = data.roots[0]
    for b in root.tree():
        name = getattr(b, 'name', b'').decode(errors='ignore')
        angle = arm if name.endswith(' UpperArm') else thigh if name.endswith(' Thigh') else calf if name.endswith(' Calf') else 0
        if angle:
            delta = N.Quaternion()
            delta.w = math.cos(math.radians(angle)/2)
            if name.endswith(' UpperArm'):
                delta.y = math.sin(math.radians(angle)/2) * (1 if ' L ' in name else -1)
            else:
                delta.z = math.sin(math.radians(angle)/2)
            b.rotation = qmatrix(qmul(b.rotation.get_scale_quat()[1], delta))
    print('angles', arm, thigh, calf)
    for b in root.tree():
        name = getattr(b, 'name', b'').decode(errors='ignore')
        if name in ('Bip01 L Calf', 'Bip01 L Foot', 'Bip01 L UpperArm', 'Bip01 L Forearm', 'Bip01 L Hand'):
            print(name, vec(b.get_transform(root).get_translation()))

if __name__ == '__main__':
    for args in ((15, 8, -16), (-15, 8, -16), (25, 0, 0), (-25, 0, 0)):
        probe(*args)
