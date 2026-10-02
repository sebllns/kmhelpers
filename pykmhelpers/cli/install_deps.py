"""Download and install kmtricks, kmindex and ntcard prebuilt binaries."""

import hashlib
import logging
import os
import platform
import shutil
import sys
import tarfile
import urllib.request

import click

from pykmhelpers.core.log import Log

logger = logging.getLogger(__name__)

RELEASE_URL = "https://github.com/tlemane/{name}/releases/download/v{version}/{name}-v{version}-{os}-{arch}.tar.gz"
# Portable ntcard builds from the sebllns/ntCard fork (static on Linux)
NTCARD_URL = "https://github.com/sebllns/ntCard/releases/download/{version}/{file}"
NTCARD_OS = {"Linux": "linux", "macOS": "macos"}
NTCARD_ARCH = {
    "Linux": {"x86_64": "x86_64", "arm64": "aarch64"},
    "macOS": {"x86_64": "x86_64", "arm64": "arm64"},
}
TARGETS = ["x86_64", "arm64"]
MACHINE_TO_TARGET = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
}
SYSTEM_TO_OS = {"Linux": "Linux", "Darwin": "macOS"}


def detect_os() -> str:
    system = platform.system()
    if system not in SYSTEM_TO_OS:
        raise click.ClickException(f"Unsupported operating system: {system}")
    return SYSTEM_TO_OS[system]


def detect_target() -> str:
    machine = platform.machine().lower()
    if machine not in MACHINE_TO_TARGET:
        raise click.ClickException(
            f"Cannot detect architecture from '{machine}', use --target"
        )
    return MACHINE_TO_TARGET[machine]


def install_release(name: str, version: str, os_name: str, target: str, path: str):
    """Download a release tarball and extract the files under its bin/ directory."""
    url = RELEASE_URL.format(name=name, version=version, os=os_name, arch=target)
    logger.info(f"Downloading {url}")
    installed = []
    # Stream mode: members are read sequentially without writing the archive to disk
    with urllib.request.urlopen(url) as response, tarfile.open(
        fileobj=response, mode="r|gz"
    ) as tar:
        for member in tar:
            if not member.isfile():
                continue
            if os.path.basename(os.path.dirname(member.path)) != "bin":
                continue
            dest = os.path.join(path, os.path.basename(member.path))
            src = tar.extractfile(member)
            assert src is not None
            # Remove first so an existing symlink is replaced, not written through
            if os.path.lexists(dest):
                os.remove(dest)
            with open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(dest, 0o755)
            installed.append(dest)
    if not installed:
        raise click.ClickException(f"No binary found in {url}")
    for dest in installed:
        logger.info(f"Installed {dest}")


def install_ntcard(version: str, os_name: str, target: str, path: str):
    """Download the ntcard binary and verify it against the release checksums."""
    suffix = f"{version}-{NTCARD_OS[os_name]}-{NTCARD_ARCH[os_name][target]}"
    name = f"ntcard-{suffix}"
    url = NTCARD_URL.format(version=version, file=name)
    logger.info(f"Downloading {url}")
    with urllib.request.urlopen(url) as response:
        data = response.read()
    sums_url = NTCARD_URL.format(version=version, file=f"SHA256SUMS-{suffix}")
    with urllib.request.urlopen(sums_url) as response:
        sums = response.read().decode()
    expected = {}
    for line in sums.splitlines():
        digest, file = line.split()
        expected[file] = digest
    if hashlib.sha256(data).hexdigest() != expected.get(name):
        raise click.ClickException(f"Checksum mismatch for {url}")
    dest = os.path.join(path, "ntcard")
    if os.path.lexists(dest):
        os.remove(dest)
    with open(dest, "wb") as out:
        out.write(data)
    os.chmod(dest, 0o755)
    logger.info(f"Installed {dest}")


@click.command(name="install-deps")
@click.option(
    "--kmtricks",
    "kmtricks_version",
    metavar="VERSION",
    default="1.6.0",
    show_default=True,
    help="kmtricks version to install (0 to skip).",
)
@click.option(
    "--kmindex",
    "kmindex_version",
    metavar="VERSION",
    default="0.6.1",
    show_default=True,
    help="kmindex version to install (0 to skip).",
)
@click.option(
    "--ntcard",
    "ntcard_version",
    metavar="VERSION",
    default="1.2.2-portable1",
    show_default=True,
    help="ntcard release tag to install (0 to skip).",
)
@click.option(
    "--target",
    type=click.Choice(TARGETS),
    default=None,
    help="Target architecture. Default: detected from the current machine.",
)
@click.option(
    "--path",
    "bin_path",
    metavar="DIR",
    type=click.Path(file_okay=False, dir_okay=True),
    default=None,
    help="Installation directory. Default: directory of the kmhelpers executable.",
)
@click.pass_context
def install_deps(
    ctx, kmtricks_version, kmindex_version, ntcard_version, target, bin_path
):
    """Download and install kmtricks, kmindex and ntcard prebuilt binaries.

    \b
    Binaries are fetched from the GitHub releases of
    github.com/tlemane/kmtricks, github.com/tlemane/kmindex and
    github.com/sebllns/ntCard (portable builds of ntCard).
    Existing files with the same name are overwritten after confirmation.
    """
    os_name = detect_os()
    target = target or detect_target()
    bin_path = os.path.abspath(
        bin_path or os.path.dirname(os.path.abspath(sys.argv[0]))
    )

    tools = [
        (name, version.lstrip("v"))
        for name, version in (
            ("kmtricks", kmtricks_version),
            ("kmindex", kmindex_version),
            ("ntcard", ntcard_version),
        )
        if version != "0"
    ]
    if not tools:
        logger.warning("Nothing to install")
        return

    existing = [
        os.path.join(bin_path, name)
        for name, _ in tools
        if os.path.exists(os.path.join(bin_path, name))
    ]
    if (
        existing
        and not (ctx.obj or {}).get("yes", False)
        and not click.confirm(f"Overwrite {', '.join(existing)}?", default=True)
    ):
        raise click.Abort()

    try:
        os.makedirs(bin_path, exist_ok=True)
        for name, version in tools:
            if name == "ntcard":
                install_ntcard(version, os_name, target, bin_path)
            else:
                install_release(name, version, os_name, target, bin_path)
        path_dirs = [
            os.path.abspath(p)
            for p in os.environ.get("PATH", "").split(os.pathsep)
            if p
        ]
        if bin_path not in path_dirs:
            logger.warning(f"{bin_path} is not in PATH")
        logger.info("SUCCESS ('install-deps')")
    except click.ClickException:
        raise
    except Exception as e:
        Log.handle_exception(logger, e, "FAILED ('install-deps')")
        raise click.ClickException("FAILED ('install-deps')")
