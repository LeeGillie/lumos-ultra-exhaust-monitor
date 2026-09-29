"""Cut the LumosAir 60 s video from the rendered frames.

Run:  blender -b --factory-startup --python compose_video.py [-- test]
Reads   renders/video/f_0001..1800.png  and  renders/video_overlays/*.png
Writes  renders/LumosAir_nodes_60s.mp4   (H.264, 1920x1080, 30 fps)
"""
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'renders', 'video')
OV = os.path.join(HERE, 'renders', 'video_overlays')
OUT = os.path.join(HERE, 'renders', 'LumosAir_nodes_60s.mp4')
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


# titles (lower third)
overlay('title_01_intro.png', 15, 125, 4)
overlay('title_02_laser.png', 165, 110, 4)
overlay('title_03_fan.png', 982, 110, 4)

# desktop-app flashes (full frame, ~1.4 s each)
FLASH = 42
for name, f in [('app_01_healthy.png', 330), ('app_02_clog-and-bin-leak.png', 520),
                ('app_03_pitot-clogged.png', 690), ('app_04_outlet-blocked.png', 1200),
                ('app_05_low-fan-level.png', 1400), ('app_06_today-no-separator.png', 1600)]:
    overlay(name, f, FLASH, 3)

r = sc.render
if hasattr(r.image_settings, 'media_type'):
    r.image_settings.media_type = 'VIDEO'
r.image_settings.file_format = 'FFMPEG'
r.ffmpeg.format = 'MPEG4'
r.ffmpeg.codec = 'H264'
r.ffmpeg.constant_rate_factor = 'HIGH'
r.ffmpeg.ffmpeg_preset = 'GOOD'
r.ffmpeg.audio_codec = 'NONE'
r.use_sequencer = True
r.filepath = OUT
if TEST:
    sc.frame_end = min(len(files), N)
    r.filepath = OUT.replace('.mp4', '_partial.mp4')
bpy.ops.render.render(animation=True)
print('WROTE', r.filepath)
