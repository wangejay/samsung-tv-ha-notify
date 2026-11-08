#!/usr/bin/env bash
# Build only an unsigned receiver. Never signs, installs, or contacts a TV.
set -euo pipefail
task_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_python="${TASK_PYTHON:-python3}"
exec "$task_python" - "$task_repo_root" "$@" <<'PY'
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

root = Path(sys.argv[1])
parser = argparse.ArgumentParser(description="Clean unsigned Tizen receiver build")
parser.add_argument("--output", type=Path, default=root / "dist" / "tv")
parser.add_argument("--offline", action="store_true", help="Use cached NuGet packages only; no package sources")
args = parser.parse_args(sys.argv[2:])
output = args.output.expanduser().resolve()
output.mkdir(parents=True, exist_ok=True)
cache = output / ".cache"
cache.mkdir(exist_ok=True)
dotnet_name = os.environ.get("TASK_DOTNET", "dotnet")
dotnet_found = shutil.which(dotnet_name)
if not dotnet_found:
    sys.exit("Install the official .NET 6.0.428 SDK, then set TASK_DOTNET to its dotnet executable.")
dotnet = Path(dotnet_found).resolve()
sdk_root = dotnet.parent
manifest = sdk_root / "sdk-manifests/6.0.400/samsung.net.sdk.tizen/WorkloadManifest.json"
if not manifest.is_file() or json.loads(manifest.read_text()).get("version") != "9.0.104":
    sys.exit("This SDK root needs Samsung's official Tizen workload 9.0.104 for SDK band 6.0.400.")

env = os.environ.copy()
env.update({
    "DOTNET_ROOT": str(sdk_root),
    "DOTNET_CLI_HOME": str(cache / "cli-home"),
    "NUGET_PACKAGES": os.environ.get("TASK_NUGET_PACKAGES", str(cache / "packages")),
    "NUGET_HTTP_CACHE_PATH": str(cache / "http-cache"),
    "DOTNET_MULTILEVEL_LOOKUP": "0",
    "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    "DOTNET_NOLOGO": "1",
    "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false",
    "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "true",
    "XDG_CONFIG_HOME": str(cache / "xdg-config"),
    "XDG_CACHE_HOME": str(cache / "xdg-cache"),
    "TMPDIR": str(cache / "tmp"),
})
Path(env["TMPDIR"]).mkdir(exist_ok=True)
source_names = ["Program.cs", "SmittyOverlay.csproj", "tizen-manifest.xml", "global.json", "shared/res/icon.png"]
expected_members = {
    "SmittyOverlay.deps.json", "bin/SmittyOverlay.dll", "bin/SmittyOverlay.pdb",
    "bin/SmittyOverlay.runtimeconfig.json", "shared/res/icon.png", "tizen-manifest.xml",
}
with tempfile.TemporaryDirectory(prefix="receiver-", dir=cache) as temporary:
    work = Path(temporary)
    for name in source_names:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "tv" / name, target)
    # net6.0-tizen8.0 additionally resolves Samsung.Tizen.Ref 8.0.154 from NuGet.
    feed = "" if args.offline else '<add key="nuget.org" value="https://api.nuget.org/v3/index.json" />'
    (work / "NuGet.Config").write_text("<configuration><packageSources><clear />" + feed + "</packageSources></configuration>\n")
    # Do not inherit unrelated build configuration from the checkout's ancestors.
    (work / "Directory.Build.props").write_text("<Project />\n")
    (work / "Directory.Build.targets").write_text("<Project />\n")
    version = subprocess.check_output([str(dotnet), "--version"], cwd=work, env=env, text=True).strip()
    if version != "6.0.428":
        sys.exit("Expected .NET SDK 6.0.428, got " + version)
    common = ["-property:Configuration=Release", "-property:Deterministic=true",
              "-property:ContinuousIntegrationBuild=true", "-property:PathMap=" + str(work) + "=/_/receiver"]
    commands = [
        ["build", "SmittyOverlay.csproj", "--nologo", "-property:TizenCreateTpkOnBuild=false"] + common,
        ["msbuild", "SmittyOverlay.csproj", "-nologo",
         "-target:ResolveReferences;_CheckApiVersion;_TizenPrepareTpkPackage;TizenCheckExecFileExist",
         "-property:TizenCreateTpkOnBuild=true"] + common,
    ]
    for index, command in enumerate(commands):
        result = subprocess.run([str(dotnet)] + command, cwd=work, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / ("build.log" if index == 0 else "stage.log")).write_text(result.stdout)
        print(result.stdout, end="")
        if result.returncode:
            sys.exit(result.returncode)
    stage = work / "bin/Release/net6.0-tizen8.0/tpkroot"
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    members = {path.relative_to(stage).as_posix() for path in files}
    if members != expected_members:
        sys.exit("Unexpected unsigned payload members: " + repr(sorted(members ^ expected_members)))
    manifest_text = (stage / "tizen-manifest.xml").read_text()
    match = re.search(r'<manifest\b[^>]*\bpackage="([A-Za-z0-9]+)"[^>]*\bversion="([0-9.]+)"', manifest_text)
    if not match:
        sys.exit("Cannot read package/version from staged manifest")
    package, package_version = match.groups()
    archive = output / (package + "-" + package_version + ".unsigned.tpk")
    # Fixed file order, permissions and timestamps; ZIP_STORED avoids zlib-version differences.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
        for path in files:
            entry = zipfile.ZipInfo(path.relative_to(stage).as_posix(), (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            z.writestr(entry, path.read_bytes())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            sys.exit("Unsigned archive CRC check failed")

digest = hashlib.sha256(archive.read_bytes()).hexdigest()
info = {
    "artifact": archive.name, "sha256": digest, "bytes": archive.stat().st_size,
    "sdk": "6.0.428", "tizen_workload": "9.0.104", "target_framework": "net6.0-tizen8.0",
    "tizen_reference_package": "8.0.154",
    "application_id": "SmittyOv01.overlay", "package_version": package_version,
    "signed": False, "zip_crc_ok": True, "members": sorted(members),
    "source_sha256": {name: hashlib.sha256((root / "tv" / name).read_bytes()).hexdigest() for name in source_names},
}
(output / "build-info.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
(output / (archive.name + ".sha256")).write_text(digest + "  " + archive.name + "\n")
print("Unsigned receiver: " + str(archive))
print("SHA-256: " + digest)
PY
