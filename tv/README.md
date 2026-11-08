# Native TV receiver

This is the minimal .NET/NUI PNG receiver, not a Web widget. Its transparent,
non-focusable notification window lets the application underneath retain remote
control input. It does not launch a video player, read phone notifications, or
monitor other apps.

The package is `SmittyOv01`, application ID **`SmittyOv01.overlay`**, version
`1.0.1`. Keep those IDs for compatibility with the project's deployment/launch
commands and upgrades. The UDP payload does not contain an application ID.
An installation of another app using these IDs will conflict; upgrades require
the same author identity.

## Source and license

Derived from [`als7294/overscreen`, `tvoverlay/`](https://github.com/als7294/overscreen/tree/c0fd412bec1a5a82f1d6a4cf867d3eb0281e55da/tvoverlay)
at commit `c0fd412bec1a5a82f1d6a4cf867d3eb0281e55da`, under the GNU General
Public License v3. The upstream license is reproduced verbatim in
[`../licenses/GPL-3.0.txt`](../licenses/GPL-3.0.txt). The project, manifest and
icon originate there; the manifest version was advanced from `1.0.0` to `1.0.1`.

Local functional changes retain all active NUI wrappers, enforce a maximum
seven-second lifetime including the fade, and clean up views, timers, animations
and temporary images on expiry or errors. An 80 ms pump checks a monotonic
deadline independently of the hold/animation callbacks. Cleanup is deferred out
of native animation callbacks. The wire format, rendering style and privileges
remain unchanged. `Program.cs` also has a portable attribution header.

## Build prerequisites

- Official **.NET SDK 6.0.428**, matching the build computer's architecture.
- Official Samsung **Tizen workload 9.0.104**, installed into that SDK's
  `6.0.400` feature band.
- Python 3 and Bash for the unsigned build script.
- First restore needs the official NuGet package **Samsung.Tizen.Ref 8.0.154**,
  because the target framework remains `net6.0-tizen8.0`. The manifest requires
  Tizen API `9.0`. Later builds can use the cached package offline.

`global.json` pins the SDK without rolling forward. No SDK, workload, NuGet
package, certificate, or pre-signed package is included in this repository.

Use Microsoft's [official .NET 6 download archive](https://dotnet.microsoft.com/en-us/download/dotnet/6.0)
to install 6.0.428 in a directory you own. Do not change your global SDK to build
this project. For example, on **macOS ARM64**:

```sh
task_tools="$HOME/.local/share/samsung-tv-ha-notify-tools"
mkdir -p "$task_tools/dotnet" "$task_tools/workload"
curl -fL https://builds.dotnet.microsoft.com/dotnet/Sdk/6.0.428/dotnet-sdk-6.0.428-osx-arm64.tar.gz \
  -o "$task_tools/dotnet-sdk.tar.gz"
shasum -a 512 "$task_tools/dotnet-sdk.tar.gz"
```

The official SHA-512 for that exact archive is:

```text
b60e74b56efc5bdb05be9c954bca6fddbc6baa79213b120fd803c75252c54cf4a6f45255b532c18ceae8c4c1c2a60d2702309156f9ab1436bd71f68947c37215
```

After verifying the checksum, extract it. Other operating systems/architectures
must use their own official archive and checksum, not this ARM64 example.

```sh
tar -xzf "$task_tools/dotnet-sdk.tar.gz" -C "$task_tools/dotnet"
export TASK_DOTNET="$task_tools/dotnet/dotnet"
curl -fL https://raw.githubusercontent.com/Samsung/Tizen.NET/5294db5380c4e5fffdaaedcf1102d944096af926/workload/scripts/workload-install.sh \
  -o "$task_tools/workload/workload-install.sh"
```

Review that official script before running it. Its SHA-256 at the pinned commit
is `05890d549275cddecab9fea079f4d47e06c12d11daf0141bfea5ebec3e5f0b60`.
Samsung documents the custom SDK directory/version options in its
[workload installation guide](https://github.com/Samsung/Tizen.NET/wiki/Installing-Tizen-.NET-Workload).
Install only into the selected, user-owned SDK directory:

```sh
(
  cd "$task_tools/workload"
  export DOTNET_CLI_HOME="$task_tools/cli-home"
  export NUGET_PACKAGES="$task_tools/nuget-packages"
  export DOTNET_CLI_TELEMETRY_OPTOUT=1
  bash ./workload-install.sh -d "$task_tools/dotnet" -v 9.0.104 -t 6.0.400
)
```

No `sudo`, global PATH edit, or shell-profile change is needed for a user-owned
SDK directory. The build script never downloads or installs an SDK/workload.

## Build an unsigned package

From the repository root:

```sh
TASK_DOTNET=/absolute/path/to/dotnet ./scripts/build-receiver.sh
# After the first successful restore:
TASK_DOTNET=/absolute/path/to/dotnet ./scripts/build-receiver.sh --offline
```

If `dotnet` is already on PATH, omit `TASK_DOTNET`. Optional `TASK_PYTHON` selects
a Python executable. `--output /path/to/output` changes the default `dist/tv/`.
`TASK_NUGET_PACKAGES` can point to an existing package cache for an offline build;
otherwise the cache is contained in the output directory.

The script copies only the five receiver source/resource files into a fresh
temporary directory. It does not import arbitrary `bin/`, `obj/`, parent build
configuration, or signing profiles. It isolates CLI home and cache directories,
does not replace `HOME`, and never contacts a TV. In online mode, package restore
uses only `https://api.nuget.org/v3/index.json`; `--offline` removes all package
sources and fails if a dependency is missing.

Outputs:

- `dist/tv/SmittyOv01-1.0.1.unsigned.tpk`
- A SHA-256 file and `build-info.json` with source hashes and member validation.
- Build/staging logs and a local cache, all outside the publishable source tree.

The package has fixed ZIP order/timestamps/permissions, and the compiler maps
temporary source paths to a stable path. It contains exactly the manifest,
receiver assembly/PDB/runtime configuration, dependency file and icon. The script
rejects additional members, including signatures or certificates. Never commit
`dist/`, SDK/cache directories, `bin/`, `obj/`, certificates, or signed TPKs.

### Exact unsigned SDK targets

The script uses these same two operations in its fresh source directory, with
additional deterministic/path-mapping properties:

```sh
"$TASK_DOTNET" build SmittyOverlay.csproj --configuration Release --nologo \
  -p:TizenCreateTpkOnBuild=false
"$TASK_DOTNET" msbuild SmittyOverlay.csproj -nologo \
  '-target:ResolveReferences;_CheckApiVersion;_TizenPrepareTpkPackage;TizenCheckExecFileExist' \
  -property:Configuration=Release -property:TizenCreateTpkOnBuild=true
```

The second command explicitly stages `bin/Release/net6.0-tizen8.0/tpkroot/`;
it does **not** invoke `_TizenTpkSign`. A normal `dotnet build` without the first
property may sign automatically using SDK test certificates, so it is not a
substitute for this unsigned workflow. The private staging target names are
specific to the pinned Samsung workload; they may change in other versions.

## Sign with your own Samsung certificates

Unsigned packages cannot be installed. Create your own **Samsung TV** certificate
profile with the official Tizen Studio Certificate Manager, including your TV's
DUID and the appropriate privilege level. Follow Samsung's
[Creating Certificates](https://developer.samsung.com/smarttv/develop/getting-started/setting-up-sdk/creating-certificates.html)
and [.NET TV application guide](https://developer.samsung.com/smarttv/develop/tizen-net-tv/getting-started/creating-net-tv-applications.html).
Generic Tizen SDK test certificates are not a replacement for a Samsung TV
distributor certificate. Keep your private keys, passwords and DUID outside the
repository; do not reuse somebody else's signed TPK.

You can use the official Visual Studio Tools for Tizen certificate/build flow.
For a CLI-only flow, Samsung's pinned .NET SDK also accepts `AuthorPath`,
`AuthorPass`, `DistributorPath` and `DistributorPass` as MSBuild properties;
these are defined in its official
[`Samsung.Tizen.Sdk.Packaging.targets`](https://github.com/Samsung/Tizen.NET/blob/5294db5380c4e5fffdaaedcf1102d944096af926/workload/src/Samsung.Tizen.Sdk/targets/Samsung.Tizen.Sdk.Packaging.targets).
For example, in a **private build copy outside this checkout**, set the paths to
your own exported `.p12` files and read passwords interactively:

```sh
(
  cd /path/to/private/receiver-copy
  export AuthorPath=/path/to/your/author.p12
  export DistributorPath=/path/to/your/samsung-tv-distributor.p12
  printf 'Author certificate password: '
  IFS= read -r -s AuthorPass
  printf '\n'
  printf 'Distributor certificate password: '
  IFS= read -r -s DistributorPass
  printf '\n'
  export AuthorPass DistributorPass
  "$TASK_DOTNET" build SmittyOverlay.csproj --configuration Release \
    -p:TizenCreateTpkOnBuild=true
)
```

Use both of your own certificate paths: leaving either unset permits the SDK's
default certificate fallback. This official SDK signing route is separate from
the unsigned script; the repository's offline verification does not exercise
signing or validate a user's certificates. SDK/tool/platform support and runtime
privilege checks still apply.

Once signed, enable Developer Mode and connect using Samsung's
[TV device instructions](https://developer.samsung.com/smarttv/develop/getting-started/using-sdk/tv-device.html).
With the official SDB tool and your own TV serial:

```sh
sdb -s "$TV_SERIAL" install /path/to/your/signed/SmittyOv01-1.0.1.tpk
sdb -s "$TV_SERIAL" shell 0 execute SmittyOv01.overlay
```

These commands are manual device changes, not part of the build script. The TV's
secure dispatcher and .NET support are firmware-dependent. A successful launch
is transparent until a PNG request arrives; an install/launch acknowledgment does
not by itself demonstrate that an overlay was shown.

## Wire protocol and runtime limits

Send one UTF-8 JSON datagram to the TV's UDP port `18110`:

```json
{"id":"example-1","url":"http://<RELAY_IPV4>:8795/media/banner.png","x":1400,"y":40,"w":480,"h":83,"ms":7000}
```

The relay must serve the PNG over HTTP from the same literal IPv4 address that
sends the datagram. Size is clamped to `10..1920` by `10..1080`; duration is
clamped to `1000..7000` milliseconds including the exit fade. Requests are queued.
`ack example-1` means the PNG downloaded and entered the queue, **not** that it was
displayed. The receiver has no text renderer, TLS or authentication; use it only
on a trusted LAN and do not expose its UDP/HTTP endpoints to the Internet.

The duration guard runs on the NUI loop at 80 ms intervals; it is not a hard
real-time guarantee if the entire application/main loop is paused. Privilege
acceptance and overlay coexistence can vary by TV firmware/application. This
version was observed working on a Q60D with Tizen 9, including continuing video,
remote input, and automatic seven-second dismissal; that is not a promise of
support for every TV or streaming app.
