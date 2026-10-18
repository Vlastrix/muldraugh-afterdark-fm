"""Build Windows player downloads and a separate Steam Workshop upload folder."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from generate_artwork import generate

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"
NAME = "MuldraughAfterdarkFM"
BANNED = {".exe", ".dll", ".bat", ".cmd", ".app", ".dylib", ".sh", ".so", ".zip", ".ps1", ".py"}


def zip_folder(folder, destination):
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder))


def validate_workshop(folder):
    contents = folder / "Contents"
    for path in contents.rglob("*"):
        if path.is_file() and path.suffix.lower() in BANNED:
            raise ValueError("Executable/developer file in Workshop content: " + str(path))
    from PIL import Image
    preview = folder / "preview.png"
    with Image.open(preview) as image:
        if image.size not in ((256, 256), (512, 512)) or image.format != "PNG":
            raise ValueError("Workshop preview must be a 256px or 512px square PNG")
    if preview.stat().st_size > 1024000:
        raise ValueError("Workshop preview exceeds the game's size limit")
    if not (contents / "mods" / "PearCarRadio" / "42" / "mod.info").is_file():
        raise ValueError("Workshop mod.info missing")


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows companion on Windows.")
    generate()
    output = ROOT / "dist" / VERSION
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / ".tools"
    scratch.mkdir(exist_ok=True)
    # All temporary build cleanup stays under this explicit workspace directory.
    with tempfile.TemporaryDirectory(prefix="release-", dir=str(scratch)) as temporary:
        staging = Path(temporary)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--noupx",
            "--name", NAME, "--icon", str(ROOT / "assets" / "app.ico"),
            "--add-data", str(ROOT / "assets" / "app.ico") + ";assets",
            "--distpath", str(staging / "binaries"), "--workpath", str(staging / "build"),
            "--specpath", str(staging), str(ROOT / "bridge" / "desktop_app.py")
        ], cwd=str(ROOT), check=True)
        executable = staging / "binaries" / (NAME + ".exe")
        report = staging / "smoke-test.json"
        environment = os.environ.copy()
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        subprocess.run([str(executable), "--self-test", str(report)], check=True, timeout=45, env=environment)
        health = json.loads(report.read_text(encoding="utf-8"))
        if not health.get("frozen") or not health.get("window_created"):
            raise ValueError("Packaged app smoke test failed")
        print("Packaged GUI smoke test:", health)
        companion = staging / "player-download"
        companion.mkdir()
        shutil.copy2(executable, companion / executable.name)
        shutil.copy2(ROOT / "docs" / "QUICK_START.txt", companion / "QUICK_START.txt")
        licenses = companion / "licenses"
        licenses.mkdir()
        shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
        tk_license = Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms"
        if tk_license.exists():
            shutil.copy2(tk_license, licenses / "Tk-license.terms")
        for package in ("pyinstaller", "pyinstaller-hooks-contrib"):
            distribution = importlib.metadata.distribution(package)
            for item in distribution.files or []:
                if "license" in str(item).lower() or "copying" in str(item).lower():
                    source = distribution.locate_file(item)
                    if source.is_file():
                        shutil.copy2(source, licenses / (package + "-" + source.name))
        shutil.copy2(ROOT / "docs" / "THIRD_PARTY_NOTICES.txt", companion / "THIRD_PARTY_NOTICES.txt")
        zip_folder(companion, output / (NAME + "-Windows-" + VERSION + ".zip"))
        shutil.copy2(executable, output / executable.name)

        workshop = staging / "Workshop" / NAME
        mod_target = workshop / "Contents" / "mods" / "PearCarRadio"
        shutil.copytree(ROOT / "mod" / "PearCarRadio", mod_target)
        shutil.copy2(ROOT / "assets" / "workshop-preview.png", workshop / "preview.png")
        shutil.copy2(ROOT / "workshop" / "workshop.txt", workshop / "workshop.txt")
        validate_workshop(workshop)
        zip_folder(workshop.parent, output / (NAME + "-Workshop-" + VERSION + ".zip"))
        unpacked = output / "Workshop" / NAME
        shutil.copytree(workshop, unpacked, dirs_exist_ok=True)

    checksums = []
    for file in sorted(output.iterdir()):
        if file.is_file() and file.suffix in (".exe", ".zip"):
            checksums.append(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name)
    (output / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print("Player and Workshop packages ready:", output)


if __name__ == "__main__":
    main()
