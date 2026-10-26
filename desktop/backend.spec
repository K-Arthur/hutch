"""Freeze the owned Python backend and its internal worker entry points.

Built on the target OS; this does not cross-compile native dependencies.
"""
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
data, binaries, imports = collect_all("hutch")
# Explicitly include the selected native backend. Runtime selection never discovers plugins.
if sys.platform in ("win32", "darwin"):
    selected_keyring = "keyring.backends.Windows" if sys.platform == "win32" else "keyring.backends.macOS"
    imports += collect_submodules(selected_keyring)
    data += copy_metadata("keyring", recursive=True)
oauth_input = os.environ.get("HUTCH_BUILD_OAUTH_APPS")
if oauth_input:
    # Replace the empty development registration, never append a competing copy.
    data = [(source, dest) for source, dest in data if Path(source).name != "oauth-apps.json"]
    data.append((oauth_input, "hutch/data"))
data += copy_metadata("hutch", recursive=True)
a = Analysis([str(root / "desktop/backend_entry.py")], pathex=[str(root / "src")],
    binaries=binaries, datas=data, hiddenimports=imports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="hutch-backend",
    debug=False, strip=False, upx=False, console=True)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="hutch-backend")
