import DaVinciResolveScript as d, time
resolve = d.scriptapp('Resolve')
proj = resolve.GetProjectManager().GetCurrentProject()
resolve.OpenPage('deliver')
proj.DeleteAllRenderJobs()
proj.SetCurrentRenderFormatAndCodec('mp4', 'H264')
proj.SetRenderSettings({
    'SelectAllFrames': True,
    'TargetDir': r"D:\DevHome\Lumos Ultra Exhaust\LumosAir\docs\3D Models\Project\renders\edit",
    'CustomName': 'LumosAir_intro_VO_v3',
    'FormatWidth': 1920, 'FormatHeight': 1080, 'FrameRate': 30,
    'ExportVideo': True, 'ExportAudio': True,
    'VideoQuality': 0, 'AudioCodec': 'aac', 'AudioBitDepth': 16, 'AudioSampleRate': 48000,
})
job = proj.AddRenderJob()
proj.StartRendering([job])
t0 = time.time()
while proj.IsRenderingInProgress() and time.time() - t0 < 50:
    time.sleep(2)
print('status', proj.GetRenderJobStatus(job))


