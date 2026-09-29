import DaVinciResolveScript as d
P = r"D:\DevHome\Lumos Ultra Exhaust\LumosAir\docs\3D Models\Project\renders"
resolve = d.scriptapp('Resolve')
pm = resolve.GetProjectManager()
proj = pm.GetCurrentProject()
if not proj or proj.GetName() != 'LumosAir videos':
    proj = pm.LoadProject('LumosAir videos')
mp = proj.GetMediaPool()
root = mp.GetRootFolder()
have = {c.GetName(): c for c in root.GetClipList()}
need = [P + r"\edit\Isotope_intro_9s.mp4", P + r"\edit\LumosAir_VO_v3.wav"]
for c in mp.ImportMedia([n for n in need if n.split('\\')[-1] not in have]) or []:
    have[c.GetName()] = c
intro, vo = have['Isotope_intro_9s.mp4'], have['LumosAir_VO_v3.wav']
c1, c2 = have['LumosAir_nodes_60s.mp4'], have['LumosAir_inside_exploded_60s.mp4']
NAME = 'LumosAir - intro + VO v3'
for i in range(1, proj.GetTimelineCount() + 1):
    t = proj.GetTimelineByIndex(i)
    if t.GetName() == NAME:
        mp.DeleteTimelines([t]); break
tl = mp.CreateEmptyTimeline(NAME)
proj.SetCurrentTimeline(tl)
tl.AddTrack('audio', 'stereo')
s0 = tl.GetStartFrame()
mp.AppendToTimeline([intro, c1, c2])
v1 = tl.GetItemListInTrack('video', 1)
print('video items', [(it.GetName(), it.GetStart(), it.GetEnd()) for it in v1])
c1_start = v1[1].GetStart()
r = mp.AppendToTimeline([{'mediaPoolItem': vo, 'startFrame': 0, 'endFrame': 3599,
                          'trackIndex': 2, 'recordFrame': c1_start, 'mediaType': 2}])
print('vo placed', r and [(x.GetName(), x.GetStart(), x.GetEnd()) for x in r])
print('audio tracks', tl.GetTrackCount('audio'), [(it.GetName(), it.GetStart()) for k in range(1, tl.GetTrackCount('audio') + 1) for it in tl.GetItemListInTrack('audio', k)])
resolve.OpenPage('edit')
pm.SaveProject()
print('end', tl.GetEndFrame() - s0, 'frames')


