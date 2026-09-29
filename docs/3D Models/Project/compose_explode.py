"""Cut the LumosAir exploded-view 60 s video from the rendered frames.

Run:  blender -b --factory-startup --python compose_video.py [-- test]
Reads   renders/video/f_0001..1800.png  and  renders/video_overlays/*.png
Writes  renders/LumosAir_inside_exploded_60s.mp4   (H.264, 1920x1080, 30 fps)
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'renders', 'explode')
OV = os.path.join(HERE, 'renders', 'explode_overlays')
OUT = os.path.join(HERE, 'renders', 'LumosAir_inside_exploded_60s.mp4')
TEST = 'test' in sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else False
N = 1800
FADE = 5

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
sc.render.fps = 30
sc.view_settings.view_transform = 'Standard'   # frames are already display-referred; pass through unchanged
sc.view_settings.look = 'None'
sc.frame_start, sc.frame_end = 1, N
se = sc.sequence_editor_create()
strips = se.strips if hasattr(se, 'strips') else se.sequences

# base footage
files = sorted(f for f in os.listdir(FR) if f.startswith('f_') and f.endswith('.png'))
base = strips.new_image('render', os.path.join(FR, files[0]), 1, 1)
for f in files[1:]:
    base.elements.append(f)
base.frame_final_duration = len(files)


def fade(s, a, b, peak=1.0):
    s.blend_alpha = 0.0; s.keyframe_insert('blend_alpha', frame=a)
    s.blend_alpha = peak; s.keyframe_insert('blend_alpha', frame=a + FADE)
    s.blend_alpha = peak; s.keyframe_insert('blend_alpha', frame=b - FADE)
    s.blend_alpha = 0.0; s.keyframe_insert('blend_alpha', frame=b)


def overlay(name, start, length, ch):
    s = strips.new_image(name, os.path.join(OV, name), ch, start)
    s.frame_final_duration = length
    s.blend_type = 'ALPHA_OVER'
    fade(s, start, start + length)
    return s


# lower-third captions, timed to each layer's move
for name, f0, f1 in [('xt_01_intro.png', 15, 145), ('xt_02_lid.png', 170, 265), ('xt_03_display.png', 275, 355),
                     ('xt_04_esp32.png', 360, 440), ('xt_05_top.png', 445, 520), ('xt_06_sensor.png', 525, 610),
                     ('xt_07_ports.png', 615, 700), ('xt_08_copper.png', 1075, 1310), ('xt_09_end.png', 1700, 1796)]:
    overlay(name, f0, f1 - f0, 3)

r = sc.render
if hasattr(r.image_settings, 'media_type'):
    r.image_settings.media_type = 'VIDEO'
r.image_settings.file_format = 'FFMPEG'
r.ffmpeg.format = 'MPEG4'
r.ffmpeg.codec = 'H264'
r.ffmpeg.constant_rate_factor = 'HIGH'
r.ffmpeg.ffmpeg_preset = 'GOOD'
r.ffmpeg.audio_codec = 'NONE'
try:  # Blender 5 video output can carry its own view transform; force pass-through
    r.image_settings.color_management = 'OVERRIDE'
    r.image_settings.view_settings.view_transform = 'Standard'
    r.image_settings.view_settings.look = 'None'
except Exception as e:
    print('colour override not available:', e)
print('video view transform:', r.image_settings.color_management,
      getattr(r.image_settings, 'view_settings', sc.view_settings).view_transform)
r.use_sequencer = True
r.filepath = OUT
if TEST:
    sc.frame_end = min(len(files), N)
    r.filepath = OUT.replace('.mp4', '_partial.mp4')
bpy.ops.render.render(animation=True)
print('WROTE', r.filepath)
