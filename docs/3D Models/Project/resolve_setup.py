import DaVinciResolveScript as d
R = r"D:\DevHome\Lumos Ultra Exhaust\LumosAir\docs\3D Models\Project\renders"
resolve = d.scriptapp('Resolve')
pm = resolve.GetProjectManager()
proj = pm.LoadProject('LumosAir videos') or pm.CreateProject('LumosAir videos')
proj.SetSetting('timelineResolutionWidth', '1920')
proj.SetSetting('timelineResolutionHeight', '1080')
proj.SetSetting('timelineFrameRate', '30')
mp = proj.GetMediaPool()
clips = mp.ImportMedia([R + r"\LumosAir_nodes_60s.mp4", R + r"\LumosAir_inside_exploded_60s.mp4"])
print('imported', [c.GetName() for c in clips])
tl = proj.GetCurrentTimeline()
if not tl or tl.GetName() != 'LumosAir 2-min':
    tl = mp.CreateTimelineFromClips('LumosAir 2-min', clips)
proj.SetCurrentTimeline(tl)
resolve.OpenPage('edit')
pm.SaveProject()
print('timeline', tl.GetName(), tl.GetStartFrame(), tl.GetEndFrame(), 'items', len(tl.GetItemListInTrack('video', 1)))
