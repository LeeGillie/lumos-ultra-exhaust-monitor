"""Exploded-view animation for Node_explode.blend (60 s @ 30 fps). Re-runnable.
Objects were tagged with custom property 'xgrp' by the setup step; every mover is a direct
child of 'Turntable pivot' (identity) except the lid screws (children of the lid), so
delta_location is a world-space offset.
"""
import bpy, math
from mathutils import Vector

sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 1800
sc.render.fps = 30
O = bpy.data.objects

# ---------------------------------------------------------------- layout (world offsets, mm)
B, T, AD, ESP, DISP = 45.0, 80.0, 115.0, 135.0, 170.0
PRES = Vector((0.0, -140.0, 105.0))          # bottom-board presentation offset (from rest)

# group: list of (frame, (dx,dy,dz))  -- BEZIER, auto-clamped handles
def seq(*pairs):
    return [(f, Vector(v)) for f, v in pairs]

Z = (0, 0, 0)
G = {
    'lidscrew':      seq((150, Z), (190, (0, 0, 25)), (1695, (0, 0, 25)), (1735, Z)),
    'lid':           seq((180, Z), (260, (0, 0, 70)), (330, (0, 0, 420)), (1580, (0, 0, 420)), (1640, (0, 0, 70)), (1690, Z)),
    'cable':         None,  # hidden while exploded
    'display':       seq((280, Z), (350, (0, 0, DISP)), (1570, (0, 0, DISP)), (1640, Z)),
    'disp_screw':    seq((270, Z), (345, (0, 0, DISP + 14)), (1575, (0, 0, DISP + 14)), (1645, Z)),
    'disp_standoff': seq((300, Z), (370, (0, 0, DISP - 6)), (1560, (0, 0, DISP - 6)), (1630, Z)),
    'esp32':         seq((350, Z), (420, (0, 0, ESP)), (1545, (0, 0, ESP)), (1610, Z)),
    'ad_screw':      seq((345, Z), (415, (0, 0, AD + 16)), (1550, (0, 0, AD + 16)), (1615, Z)),
    'adapter':       seq((360, Z), (430, (0, 0, AD)), (1535, (0, 0, AD)), (1600, Z)),
    'ad_standoff':   seq((380, Z), (450, (0, 0, 100)), (1525, (0, 0, 100)), (1590, Z)),
    'disp_nut':      seq((390, Z), (460, (0, 0, T - 10)), (1520, (0, 0, T - 10)), (1585, Z)),
    'ad_nut':        seq((390, Z), (460, (0, 0, T - 10)), (1520, (0, 0, T - 10)), (1585, Z)),
    'box_screw':     seq((400, Z), (470, (0, 0, T + 12)), (1510, (0, 0, T + 12)), (1575, Z)),
    'top':           seq((410, Z), (480, (0, 0, T)), (1505, (0, 0, T)), (1570, Z)),
    'box_standoff':  seq((440, Z), (510, (0, 0, 60)), (1490, (0, 0, 60)), (1550, Z)),
    'bottom':        seq((470, Z), (550, (0, 0, B)),
                         (985, (0, 0, B)), (1015, (0, -140, B + 20)), (1060, PRES),        # slide out & up
                         (1330, PRES), (1380, (0, -140, B + 20)), (1410, (0, 0, B)),      # back
                         (1460, (0, 0, B)), (1530, Z)),
    'bulk_px':       seq((520, Z), (590, (22, 0, 0)), (1440, (22, 0, 0)), (1500, Z)),
    'bulk_mx':       seq((520, Z), (590, (-22, 0, 0)), (1440, (-22, 0, 0)), (1500, Z)),
    'usb_sock':      seq((540, Z), (610, (0, -24, 0)), (1440, (0, -24, 0)), (1500, Z)),
    'fan_sock':      seq((540, Z), (610, (0, 24, 0)), (1440, (0, 24, 0)), (1500, Z)),
}
FLIP = [(1065, 0.0), (1125, math.pi), (1275, math.pi), (1330, 0.0)]     # bottom board about its Y axis
SPIN = [(1065, 0.0), (1125, math.radians(-12)), (1275, math.radians(12)), (1330, 0.0)]


def clear(o):
    if o.animation_data:
        o.animation_data_clear()


def key_delta(o, keys):
    for f, v in keys:
        o.delta_location = v
        o.keyframe_insert('delta_location', frame=f)


def fcurves(o):
    ad = o.animation_data
    act = ad.action
    if hasattr(act, 'fcurves') and len(act.fcurves):
        return list(act.fcurves)
    out = []
    for L in act.layers:
        for st in L.strips:
            cb = st.channelbag(ad.action_slot)
            if cb:
                out += list(cb.fcurves)
    return out


def ease(o):
    for fc in fcurves(o):
        for k in fc.keyframe_points:
            k.interpolation = 'BEZIER'
            k.handle_left_type = k.handle_right_type = 'AUTO_CLAMPED'
        fc.update()


movers = [o for o in sc.objects if 'xgrp' in o.keys()]
for o in movers:
    clear(o)
    o.delta_location = (0, 0, 0)
    o.delta_rotation_euler = (0, 0, 0)
    o.hide_render = False
for o in movers:
    g = o['xgrp']
    if g == 'cable':
        for f, h in ((1, False), (275, True), (1640, False)):
            o.hide_render = h
            o.keyframe_insert('hide_render', frame=f)
            o.hide_viewport = False
        continue
    key_delta(o, G[g])
    if g == 'bottom':
        for f, a in FLIP:
            o.delta_rotation_euler = (0, a, 0)
            o.keyframe_insert('delta_rotation_euler', index=1, frame=f)
        for f, a in SPIN:
            o.delta_rotation_euler = (0, o.delta_rotation_euler[1], a)
            o.keyframe_insert('delta_rotation_euler', index=2, frame=f)
    ease(o)
    if g == 'cable':
        continue

# ---------------------------------------------------------------- camera (PCHIP through waypoints)
# frame, azimuth deg, elevation deg, distance, target xyz
CAM = [
    (1,    215, 30, 540, (0, 175, 22)),
    (150,  228, 32, 500, (0, 175, 24)),
    (260,  236, 30, 640, (0, 175, 55)),
    (430,  245, 24, 980, (0, 175, 105)),
    (620,  245, 23, 1180, (0, 175, 120)),
    (960,  245, 25, 1180, (0, 175, 120)),
    (1060, 232, 42, 520, (0, 35, 118)),          # follow the sensor board out
    (1140, 228, 52, 330, (0, 35, 114)),
    (1270, 240, 56, 290, (0, 35, 114)),
    (1340, 240, 40, 640, (0, 90, 110)),
    (1440, 245, 26, 1120, (0, 175, 108)),
    (1560, 240, 28, 820, (0, 175, 60)),
    (1700, 225, 30, 540, (0, 175, 24)),
    (1800, 218, 31, 520, (0, 175, 22)),
]


def pchip(xs, ys):
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = m[-1] = 0.0

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = max(k for k in range(n - 1) if xs[k] <= x)
        t = (x - xs[i]) / h[i]
        h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


fs = [c[0] for c in CAM]
F_az = pchip(fs, [c[1] for c in CAM]); F_el = pchip(fs, [c[2] for c in CAM]); F_d = pchip(fs, [c[3] for c in CAM])
F_t = [pchip(fs, [c[4][i] for c in CAM]) for i in range(3)]
cam, tgt = O['Camera'], O['Camera target']
clear(cam); clear(tgt)
sc.camera = cam
cam.data.lens = 85
for f in range(1, 1801):
    az, el, d = math.radians(F_az(f)), math.radians(F_el(f)), F_d(f)
    t = Vector([F_t[i](f) for i in range(3)])
    tgt.location = t
    cam.location = t + d * Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    tgt.keyframe_insert('location', frame=f)
    cam.keyframe_insert('location', frame=f)
for o in (cam, tgt):
    for fc in fcurves(o):
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
# turntable: model orbit (keeps the studio backdrop behind it)
piv = O['Turntable pivot']
clear(piv)
for f, d in ((1, -18), (560, 0), (620, 0), (980, 360), (1440, 360), (1800, 372)):
    piv.rotation_euler = (0, 0, math.radians(d))
    piv.keyframe_insert('rotation_euler', index=2, frame=f)
ease(piv)
sw = O['Studio sweep']
sw.scale = (2.5, 2.5, 2.5); sw.location = (0, 175 - 2.5 * 175, 0)
print('explode animation set:', len(movers), 'movers')
