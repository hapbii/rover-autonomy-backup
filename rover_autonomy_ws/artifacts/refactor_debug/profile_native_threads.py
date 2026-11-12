import ctypes
import gc
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import memory_lifecycle as probe

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenThread.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
kernel.OpenThread.restype = ctypes.c_void_p
kernel.GetThreadDescription.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
kernel.CloseHandle.argtypes = [ctypes.c_void_p]
kernel.LocalFree.argtypes = [ctypes.c_void_p]


def threads(process):
    result = []
    for value in process.threads():
        handle = kernel.OpenThread(0x0800, False, value.id)
        name = ctypes.c_wchar_p()
        try:
            if handle and kernel.GetThreadDescription(handle, ctypes.byref(name)) == 0:
                result.append({"id": value.id, "name": name.value,
                               "cpu": value.user_time + value.system_time})
            else:
                result.append({"id": value.id, "name": "unavailable"})
        finally:
            if name:
                kernel.LocalFree(ctypes.cast(name, ctypes.c_void_p))
            if handle:
                kernel.CloseHandle(handle)
    return result


probe.cv2.setNumThreads(1)
reference = probe.cv2.imdecode(probe.np.fromfile(ROOT / "tests/assets/palm_reference.png", probe.np.uint8), 1)
config = probe.HardwareConfig(enabled=True, calibrated=True, wheel_radius_m=0.03,
                             track_width_m=0.2, encoder_ticks_per_rev=960)
process = probe.psutil.Process()
observations = []
with tempfile.TemporaryDirectory(prefix="native_thread_probe_") as directory:
    video = Path(directory) / "reference.mp4"
    probe.write_video(video, reference)
    for cycle in range(401):
        if cycle:
            probe.one_cycle(video, config)
        if cycle % 20 == 0:
            gc.collect()
            state = {"cycle": cycle, "rss": process.memory_info().rss,
                     "handles": process.num_handles(), "threads": threads(process)}
            observations.append(state)
            print(json.dumps({"cycle": cycle, "rss": state["rss"],
                              "handles": state["handles"], "threads": len(state["threads"])}), flush=True)
(ROOT / "artifacts/refactor_debug/native_threads.json").write_text(json.dumps(observations, indent=2))
