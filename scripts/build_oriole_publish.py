#!/usr/bin/env python3
"""Download, Magisk-patch, and sign a single OTA for oriole.

This script follows the download and patch flow from rooted-ota.sh but keeps it
local and minimal. It:
- downloads the latest GrapheneOS OTA for oriole
- patches it with Magisk (preinit device: metadata)
- signs the OTA with keys from the local keys/ folder
- writes Custota files into publish/

Outputs:
- publish/<ota-zip>
- publish/<ota-zip>.csig
- publish/magisk/oriole.json
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from platform import uname

# Fixed per request
DEVICE_ID = "oriole"
MAGISK_PREINIT_DEVICE = "metadata"
GRAPHENE_TYPE = "ota_update"
OTA_CHANNEL = "stable-security-preview"

# Versions aligned with rooted-ota.sh
DEFAULT_MAGISK_VERSION = "v30.7"
AVB_ROOT_VERSION = "3.29.1"
CUSTOTA_VERSION = "5.22"
PATCH_PY_COMMIT = "84139189c8cbe244a676582a3b3517f31fabc421"
OEMUNLOCKONBOOT_VERSION = "1.3"
AFSR_VERSION = "1.0.4"

CHENXIAOLONG_PK = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDOe6/tBnO7xZhAWXRj3ApUYgn+XZ0wnQiXM8B7tPgv4"
)

OTA_BASE_URL = "https://releases.grapheneos.org"


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    live: bool = False,
) -> None:
    cmd = " ".join(args)
    _eprint(f"+ {cmd}")
    if live:
        subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, check=True)
        return
    try:
        subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            _eprint("stdout:\n" + exc.stdout)
        if exc.stderr:
            _eprint("stderr:\n" + exc.stderr)
        raise


def _require_tools(tools: list[str]) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        raise SystemExit("Missing required tools in PATH: " + ", ".join(missing))


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _eprint(f"Downloading {url} -> {dest}")
    with urllib.request.urlopen(url) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def _read_text_url(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _latest_ota_version() -> str:
    # GrapheneOS releases endpoint returns a list, first word is version.
    txt = _read_text_url(f"{OTA_BASE_URL}/{DEVICE_ID}-{OTA_CHANNEL}")
    lines = [line.strip() for line in txt.splitlines() if line.strip()]
    if not lines:
        raise SystemExit(
            f"No OTA versions found at {OTA_BASE_URL}/{DEVICE_ID}-{OTA_CHANNEL}"
        )
    first_line = lines[0]
    return first_line.split()[0]


def _verify_sig(file_path: Path, sig_path: Path) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
        key_file.write(f"chenxiaolong {CHENXIAOLONG_PK}\n")
        key_file_path = Path(key_file.name)

    try:
        with file_path.open("rb") as fh:
            subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-I",
                    "chenxiaolong",
                    "-f",
                    str(key_file_path),
                    "-n",
                    "file",
                    "-s",
                    str(sig_path),
                ],
                cwd=str(file_path.parent),
                stdin=fh,
                check=True,
            )
    finally:
        key_file_path.unlink(missing_ok=True)


def _download_and_verify_chenxiaolong(repo: str, version: str, artifact: str | None = None) -> None:
    artifact_name = artifact or repo
    url = (
        f"https://github.com/chenxiaolong/{repo}/releases/download/v{version}/"
        f"{artifact_name}-{version}-{uname().machine}-unknown-linux-gnu.zip"
    )

    tmp_dir = WORK_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    target = tmp_dir / artifact_name
    if target.exists():
        return

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        zip_path = td_path / "download.zip"
        sig_path = td_path / "download.zip.sig"

        _download(url, zip_path)
        _download(url + ".sig", sig_path)
        _verify_sig(zip_path, sig_path)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)

        target.chmod(0o755)


def _download_magisk(magisk_version: str) -> Path:
    tmp_dir = WORK_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    apk = tmp_dir / f"magisk-{magisk_version}.apk"
    if not apk.exists():
        url = (
            "https://github.com/topjohnwu/Magisk/releases/download/"
            f"{magisk_version}/Magisk-{magisk_version}.apk"
        )
        _download(url, apk)
    return apk


def _download_ota(ota_target: str) -> Path:
    tmp_dir = WORK_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"{ota_target}.zip"
    if not zip_path.exists():
        _download(f"{OTA_BASE_URL}/{ota_target}.zip", zip_path)
    return zip_path


def _clone_my_avbroot_setup() -> Path:
    repo_dir = WORK_DIR / ".tmp" / "my-avbroot-setup"
    if repo_dir.exists():
        return repo_dir
    _run(["git", "clone", "https://github.com/chenxiaolong/my-avbroot-setup", str(repo_dir)])
    _run(["git", "checkout", PATCH_PY_COMMIT], cwd=repo_dir)
    return repo_dir


def _download_modules() -> None:
    tmp_dir = WORK_DIR / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    custota_zip = tmp_dir / "custota.zip"
    if not custota_zip.exists():
        url = (
            "https://github.com/chenxiaolong/Custota/releases/download/"
            f"v{CUSTOTA_VERSION}/Custota-{CUSTOTA_VERSION}-release.zip"
        )
        _download(url, custota_zip)
        custota_sig = tmp_dir / "custota.zip.sig"
        _download(url + ".sig", custota_sig)
        _verify_sig(custota_zip, custota_sig)

    oemunlock_zip = tmp_dir / "oemunlockonboot.zip"
    if not oemunlock_zip.exists():
        url = (
            "https://github.com/chenxiaolong/OEMUnlockOnBoot/releases/download/"
            f"v{OEMUNLOCKONBOOT_VERSION}/OEMUnlockOnBoot-{OEMUNLOCKONBOOT_VERSION}-release.zip"
        )
        _download(url, oemunlock_zip)
        oemunlock_sig = tmp_dir / "oemunlockonboot.zip.sig"
        _download(url + ".sig", oemunlock_sig)
        _verify_sig(oemunlock_zip, oemunlock_sig)


def _require_key_material() -> None:
    required = [KEYS_DIR / "avb.key", KEYS_DIR / "ota.key", KEYS_DIR / "ota.crt"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit(
            "Missing required key files in keys/: " + ", ".join(missing)
        )


def _download_dependencies(magisk_version: str, ota_target: str) -> Path:
    _download_and_verify_chenxiaolong("avbroot", AVB_ROOT_VERSION)
    _download_and_verify_chenxiaolong("afsr", AFSR_VERSION)
    _download_modules()
    _clone_my_avbroot_setup()
    magisk_apk = _download_magisk(magisk_version)
    _download_ota(ota_target)
    return magisk_apk


def _git_short_rev(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(repo_root), text=True
        )
        return out.strip()
    except subprocess.CalledProcessError:
        return "local"


def _asset_name(ota_version: str, magisk_version: str, commit: str) -> str:
    return f"{DEVICE_ID}-{ota_version}-{commit}-magisk-{magisk_version}.zip"


def _published_artifacts_exist(ota_version: str, magisk_version: str) -> bool:
    commit = _git_short_rev(REPO_ROOT)
    name = _asset_name(ota_version, magisk_version, commit)
    publish_zip = publish_dir / name
    publish_csig = publish_dir / f"{name}.csig"
    update_json = publish_dir / "magisk" / f"{DEVICE_ID}.json"
    return publish_zip.exists() and publish_csig.exists() and update_json.exists()


def _patch_ota(
    *,
    ota_target: str,
    ota_version: str,
    magisk_version: str,
    magisk_apk: Path,
) -> Path:
    tmp_dir = WORK_DIR / ".tmp"
    commit = _git_short_rev(REPO_ROOT)

    asset_name = _asset_name(ota_version, magisk_version, commit)
    output_zip = tmp_dir / asset_name
    if output_zip.exists():
        return output_zip

    key_avb = KEYS_DIR / "avb.key"
    key_ota = KEYS_DIR / "ota.key"
    cert_ota = KEYS_DIR / "ota.crt"
    for p in (key_avb, key_ota, cert_ota):
        if not p.exists():
            raise SystemExit(f"Missing key file: {p}")

    args = [
        "--output",
        str(output_zip),
        "--input",
        str(tmp_dir / f"{ota_target}.zip"),
        "--sign-key-avb",
        str(key_avb),
        "--sign-key-ota",
        str(key_ota),
        "--sign-cert-ota",
        str(cert_ota),
        "--patch-arg=--magisk",
        "--patch-arg",
        str(magisk_apk),
        "--patch-arg=--magisk-preinit-device",
        "--patch-arg",
        MAGISK_PREINIT_DEVICE,
        "--module-custota",
        str(tmp_dir / "custota.zip"),
        "--module-oemunlockonboot",
        str(tmp_dir / "oemunlockonboot.zip"),
        "--skip-custota-tool",
    ]

    env = os.environ.copy()
    if os.environ.get("PASSPHRASE_AVB"):
        env["PASSPHRASE_AVB"] = os.environ["PASSPHRASE_AVB"]
        args += ["--pass-avb-env-var", "PASSPHRASE_AVB"]
    if os.environ.get("PASSPHRASE_OTA"):
        env["PASSPHRASE_OTA"] = os.environ["PASSPHRASE_OTA"]
        args += ["--pass-ota-env-var", "PASSPHRASE_OTA"]

    tmp_bin = str((WORK_DIR / ".tmp").resolve())
    env["PATH"] = tmp_bin + os.pathsep + env.get("PATH", "")

    # Run patch.py locally (no Docker) via uv, using requirements.txt.
    patch_script = WORK_DIR / ".tmp" / "my-avbroot-setup" / "patch.py"
    if not patch_script.exists():
        raise SystemExit(f"Missing patch script: {patch_script}")

    reqs = WORK_DIR / ".tmp" / "my-avbroot-setup" / "requirements.txt"
    if not reqs.exists():
        raise SystemExit(f"Missing requirements file: {reqs}")

    _run(
        ["uv", "run", "--with-requirements", str(reqs), str(patch_script), *args],
        cwd=WORK_DIR,
        env=env,
        live=True,
    )
    return output_zip


def _download_custota_tool() -> Path:
    _download_and_verify_chenxiaolong("Custota", CUSTOTA_VERSION, "custota-tool")
    tool = WORK_DIR / ".tmp" / "custota-tool"
    if not tool.exists():
        raise SystemExit("custota-tool not found after download")
    return tool


def _generate_custota_files(ota_zip: Path, ota_version: str) -> None:
    publish_dir.mkdir(parents=True, exist_ok=True)
    (publish_dir / "magisk").mkdir(parents=True, exist_ok=True)

    tool = _download_custota_tool()

    csig = publish_dir / f"{ota_zip.name}.csig"
    csig_args = [
        str(tool),
        "gen-csig",
        "--input",
        str(ota_zip),
        "--output",
        str(csig),
        "--key",
        str(KEYS_DIR / "ota.key"),
        "--cert",
        str(KEYS_DIR / "ota.crt"),
    ]
    if os.environ.get("PASSPHRASE_OTA"):
        csig_args += ["--passphrase-env-var", "PASSPHRASE_OTA"]
    _run(csig_args, cwd=WORK_DIR, env=os.environ.copy())

    location = f"../{ota_zip.name}"
    json_path = publish_dir / "magisk" / f"{DEVICE_ID}.json"
    _run(
        [str(tool), "gen-update-info", "--file", str(json_path), "--location", location],
        cwd=WORK_DIR,
        env=os.environ.copy(),
    )


def _cleanup_old_versions() -> None:
    zips = sorted(
        publish_dir.glob(f"{DEVICE_ID}-*-magisk-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_zip in zips[2:]:
        old_zip.unlink()
        csig = publish_dir / f"{old_zip.name}.csig"
        if csig.exists():
            csig.unlink()


def main() -> int:
    _require_tools(["git", "ssh-keygen", "uv"])

    magisk_version = os.environ.get("MAGISK_VERSION", DEFAULT_MAGISK_VERSION)
    ota_version = os.environ.get("OTA_VERSION", "latest")

    if ota_version == "latest":
        ota_version = _latest_ota_version()

    ota_target = f"{DEVICE_ID}-{GRAPHENE_TYPE}-{ota_version}"
    _eprint(f"OTA target: {ota_target}")

    publish_dir.mkdir(parents=True, exist_ok=True)
    if _published_artifacts_exist(ota_version, magisk_version):
        _eprint("Publish artifacts already exist; skipping download/patch/sign")
        _cleanup_old_versions()
        return 0

    _require_key_material()

    magisk_apk = _download_dependencies(magisk_version, ota_target)
    ota_zip = _patch_ota(
        ota_target=ota_target,
        ota_version=ota_version,
        magisk_version=magisk_version,
        magisk_apk=magisk_apk,
    )

    publish_zip = publish_dir / ota_zip.name
    shutil.copy2(ota_zip, publish_zip)
    _generate_custota_files(publish_zip, ota_version)
    _cleanup_old_versions()

    _eprint(f"Done. Publish folder: {publish_dir}")
    return 0


REPO_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = REPO_ROOT / ".work"
KEYS_DIR = REPO_ROOT / "keys"
publish_dir = REPO_ROOT / "publish"

if __name__ == "__main__":
    raise SystemExit(main())
