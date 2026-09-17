"""Download and install kmtricks and kmindex prebuilt binaries."""

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
def install_deps(ctx, kmtricks_version, kmindex_version, target, bin_path):
    """Download and install kmtricks and kmindex prebuilt binaries.

    \b
    Binaries are fetched from the GitHub releases of
    github.com/tlemane/kmtricks and github.com/tlemane/kmindex.
    Existing files with the same name are overwritten after confirmation.
    """
    os_name = detect_os()
    target = target or detect_target()
    bin_path = os.path.abspath(
        bin_path or os.path.dirname(os.path.abspath(sys.argv[0]))
    )

    releases = [
        (name, version.lstrip("v"))
        for name, version in (
            ("kmtricks", kmtricks_version),
            ("kmindex", kmindex_version),
        )
        if version != "0"
    ]
    if not releases:
        logger.warning("Nothing to install")
        return

    existing = [
        os.path.join(bin_path, name)
        for name, _ in releases
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
        for name, version in releases:
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
