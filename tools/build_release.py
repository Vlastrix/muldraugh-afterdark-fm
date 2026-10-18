"""Build Windows player downloads and a separate Steam Workshop upload folder."""
import argparse
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
VERSION = "0.7.6-dev"
NAME = "MuldraughAfterdarkFM"
CONNECTOR_NAME = "AfterdarkFMConnector"
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / VERSION,
                        help="Use a separate folder when the previous build is running.")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Build the Windows Connector on Windows.")
    if sys.version_info < (3, 12):
        raise SystemExit("The experimental streaming build requires Python 3.12 or later.")
    generate()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / ".tools"
    scratch.mkdir(exist_ok=True)
    # All temporary build cleanup stays under this explicit workspace directory.
    with tempfile.TemporaryDirectory(prefix="release-", dir=str(scratch)) as temporary:
        staging = Path(temporary)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--noupx",
            "--name", CONNECTOR_NAME, "--icon", str(ROOT / "assets" / "app.ico"),
            "--add-data", str(ROOT / "assets" / "app.ico") + ";assets",
            "--distpath", str(staging / "binaries"), "--workpath", str(staging / "build"),
            "--specpath", str(staging), str(ROOT / "bridge" / "desktop_app.py")
        ], cwd=str(ROOT), check=True)
        executable = staging / "binaries" / (CONNECTOR_NAME + ".exe")
        report = staging / "smoke-test.json"
        environment = os.environ.copy()
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        subprocess.run([str(executable), "--self-test", str(report)], check=True, timeout=45, env=environment)
        health = json.loads(report.read_text(encoding="utf-8"))
        if not health.get("frozen") or not health.get("window_created") or not health.get("disconnected"):
            raise ValueError("Packaged app smoke test failed")
        print("Packaged GUI smoke test:", health)
        audio_report = staging / 'audio-smoke-test.json'
        subprocess.run([str(executable), '--self-test-audio', str(audio_report)],
                       check=True, timeout=45, env=environment)
        audio_health = json.loads(audio_report.read_text(encoding='utf-8'))
        if not audio_health.get('frozen') or not audio_health.get('native_capture_loaded'):
            raise ValueError('Packaged audio lab smoke test failed')
        print('Packaged audio lab smoke test:', audio_health)
        game_report = staging / 'game-smoke-test.json'
        subprocess.run([str(executable), '--self-test-game', str(game_report)],
                       check=True, timeout=45, env=environment)
        game_health = json.loads(game_report.read_text(encoding='utf-8'))
        if not game_health.get('frozen') or not game_health.get('opus_loaded'):
            raise ValueError('Packaged game lab smoke test failed')
        print('Packaged game lab smoke test:', game_health)
        connector = staging / "player-download"
        connector.mkdir()
        shutil.copy2(executable, connector / executable.name)
        shutil.copy2(ROOT / "docs" / "QUICK_START.txt", connector / "QUICK_START.txt")
        shutil.copy2(ROOT / 'docs' / 'AUDIO_LAB.md', connector / 'AUDIO_LAB.md')
        shutil.copy2(ROOT / 'docs' / 'GAME_LAB.md', connector / 'GAME_LAB.md')
        shutil.copy2(ROOT / 'docs' / 'RADIO_TEST.md', connector / 'RADIO_TEST.md')
        licenses = connector / "licenses"
        licenses.mkdir()
        shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
        tk_license = Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms"
        if tk_license.exists():
            shutil.copy2(tk_license, licenses / "Tk-license.terms")
        for package in ("pyinstaller", "pyinstaller-hooks-contrib", 'proc-tap', 'sounddevice', 'cryptography', 'psutil', 'numpy', 'scipy', 'cffi', 'av'):
            distribution = importlib.metadata.distribution(package)
            for item in distribution.files or []:
                if "license" in str(item).lower() or "copying" in str(item).lower():
                    source = distribution.locate_file(item)
                    if source.is_file():
                        identifier = hashlib.sha256(str(item).encode('utf-8')).hexdigest()[:8]
                        shutil.copy2(source, licenses / (package + "-" + identifier + "-" + source.name))
        shutil.copy2(ROOT / "docs" / "THIRD_PARTY_NOTICES.txt", connector / "THIRD_PARTY_NOTICES.txt")
        zip_folder(connector, output / (CONNECTOR_NAME + "-Windows-" + VERSION + ".zip"))
        shutil.copy2(executable, output / executable.name)

        workshop = staging / "Workshop" / NAME
        mod_target = workshop / "Contents" / "mods" / "PearCarRadio"
        shutil.copytree(ROOT / "mod" / "PearCarRadio", mod_target)
        # Standalone local lab ID avoids shadowing the subscribed public mod.
        test_mod = staging / 'game-test-mod' / 'AfterdarkGameLab'
        (test_mod / '42').mkdir(parents=True)
        (test_mod / '42' / 'mod.info').write_text(
            'name=Muldraugh Afterdark FM Game Lab [B42.21]\n'
            'id=AfterdarkGameLab\nauthor=DonVladi\n'
            'description=Experimental radio integration for Project Zomboid Build 42.21. Car and placed radio behavior requires multiplayer testing.\n'
            'version=' + VERSION + '\nversionMin=42.21\nposter=poster.png\n', encoding='utf-8')
        shutil.copy2(ROOT / 'assets' / 'workshop-preview.png', test_mod / '42' / 'poster.png')
        for relative in ('shared/AfterdarkGameProtocol.lua', 'shared/AfterdarkRadioDevices.lua',
                         'client/AfterdarkGameClient.lua', 'client/AfterdarkRadioClient.lua', 'client/AfterdarkRadioUI.lua',
                         'server/AfterdarkGameServer.lua', 'server/AfterdarkRadioServer.lua'):
            target = test_mod / 'common' / 'media' / 'lua' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / 'mod' / 'PearCarRadio' / 'common' / 'media' / 'lua' / relative, target)
        zip_folder(test_mod.parent, output / (NAME + '-Game-Test-' + VERSION + '.zip'))
        shutil.copytree(test_mod, output / 'Test-Mod' / 'AfterdarkGameLab', dirs_exist_ok=True)
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
