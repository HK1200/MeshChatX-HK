# SPDX-License-Identifier: 0BSD

"""Import probes for cx_Freeze desktop builds.

Invoked from CI and build-backend via:

  ReticulumMeshChatX --meshchatx-run-module meshchatx.src.backend.frozen_freeze_probe
"""

from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


def _lxst_filterlib_path() -> Path | None:
    spec = importlib.util.find_spec("LXST")
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(next(iter(spec.submodule_search_locations)))
    if not root.is_dir():
        return None
    ext = sysconfig.get_config_var("EXT_SUFFIX") or ""
    candidates: list[Path] = []
    if sys.platform == "win32":
        candidates.append(root / "filterlib.dll")
    if ext:
        candidates.append(root / f"filterlib{ext}")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _verify_security_parser() -> dict[str, str]:
    """Check the actual loaded parser, including the ElementTree C API."""
    import platform
    import pyexpat
    import xml.etree.ElementTree as ET

    versions = {"python": platform.python_version(), "expat": pyexpat.EXPAT_VERSION}
    if versions != {"python": "3.14.10", "expat": "expat_2.10.0"}:
        raise RuntimeError(f"Frozen runtime is not security fixed: {versions}")
    # Fixed synthetic XML exercises the actual native API, not untrusted input.
    node = ET.fromstring("<root><name>Alice \u2603</name></root>")  # noqa: S314
    if node.findtext("name") != "Alice \u2603":
        raise RuntimeError("Frozen ElementTree native parser Unicode check failed")
    pyexpat.ParserCreate().Parse("<verified/>", True)
    try:
        pyexpat.ParserCreate().Parse("<root>", True)
    except pyexpat.ExpatError:
        pass
    else:
        raise RuntimeError("Frozen parser accepted malformed XML")
    entities = ['<!ENTITY a0 "1234567890">']
    entities.extend(
        f'<!ENTITY a{index} "' + f"&a{index - 1};" * 10 + '">' for index in range(1, 9)
    )
    try:
        pyexpat.ParserCreate().Parse(
            "<!DOCTYPE a [" + "".join(entities) + "]><a>&a8;</a>", True
        )
    except pyexpat.ExpatError as error:
        if (
            error.code
            != pyexpat.errors.codes[pyexpat.errors.XML_ERROR_AMPLIFICATION_LIMIT_BREACH]
        ):
            raise RuntimeError(
                "Unexpected frozen parser amplification failure"
            ) from error
    else:
        raise RuntimeError("Frozen parser did not enforce entity amplification limit")
    return versions


def main() -> None:
    if getattr(sys, "frozen", False):
        print("frozen security parser", _verify_security_parser())
    import email.header
    import email.message
    import email.policy  # noqa: F401

    import aiohttp  # noqa: F401
    import LXST  # noqa: F401
    import RNS.vendor.umsgpack as umsgpack

    packed = umsgpack.packb({"probe": True})
    if umsgpack.unpackb(packed).get("probe") is not True:
        raise SystemExit("frozen-freeze-probe: RNS.vendor.umsgpack roundtrip failed")

    native = _lxst_filterlib_path()
    if native is None:
        raise SystemExit("frozen-freeze-probe: LXST filterlib native artifact missing")

    if sys.platform == "darwin":
        # The macOS slices ship libcodec2 for the ctypes binding. The pycodec2
        # extension is not part of the freeze.
        from meshchatx import pycodec2_ctypes

        codec = pycodec2_ctypes.Codec2(1600)
        if codec.samples_per_frame() <= 0:
            raise SystemExit(
                "frozen-freeze-probe: codec2 ctypes binding returned no samples"
            )

    # Import-only checks do not exercise frozen spawn dispatch. Use the actual
    # LXMF validation target so RNS/LXMF circular imports fail this build gate.
    import multiprocessing

    from LXMF.LXStamper import validate_pn_stamp

    with multiprocessing.get_context("spawn").Pool(1) as pool:
        result = pool.apply_async(validate_pn_stamp, (b"short", 1)).get(timeout=15)
    if result != (None, None, None, None):
        raise SystemExit("frozen-freeze-probe: unexpected LXMF worker result")

    print("frozen-freeze-probe ok", flush=True)


if __name__ == "__main__":
    main()
