"""Optional fresh-CLI measurements with explicit process peak semantics."""

import platform
import sys
import time


def profile_check(callback):
    if not sys.platform.startswith("linux"):
        raise ValueError("--profile peak-RSS measurement is currently Linux-only")
    import resource
    wall, cpu = time.perf_counter(), time.process_time()
    result = callback()
    result["measurements"] = {"wall_seconds": time.perf_counter() - wall,
                              "process_cpu_seconds": time.process_time() - cpu,
                              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
                              "python_version": platform.python_version(),
                              "implementation": platform.python_implementation(),
                              "platform": sys.platform,
                              "scope": "Wall/process CPU cover checker execution, excluding input reading/output serialization. RSS is the process-lifetime high-water mark including imports and CLI setup, not per-call allocation. Measurements are observations, not a hard runtime/memory limit or cross-platform benchmark."}
    return result
