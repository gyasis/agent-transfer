"""ELF binary scanner — detects compiled binaries and extracts architecture metadata.

Reads ELF magic bytes, architecture, OS/ABI, and attempts heuristic detection
of source language and build commands from surrounding project files.
"""

import struct
from pathlib import Path
from typing import List, Optional

from agent_transfer.utils.preflight.manifest import BinaryDep

# ELF magic: 0x7f followed by 'E', 'L', 'F'
_ELF_MAGIC = b"\x7fELF"

# Architecture mapping: e_machine field at offset 18 (2 bytes, little-endian)
_ARCH_MAP = {
    0x03: "x86",
    0x28: "arm",
    0x3E: "x86_64",
    0xB7: "aarch64",
}

# OS/ABI mapping: EI_OSABI at offset 7
_OSABI_MAP = {
    0x00: "linux",  # ELFOSABI_NONE / System V — standard for Linux binaries
    0x03: "linux",  # ELFOSABI_LINUX
}

# Build system indicator files and the commands they imply
_BUILD_INDICATORS = (
    ("Cargo.toml", "cargo build --release"),
    ("Makefile", "make"),
    ("CMakeLists.txt", "cmake --build ."),
)

# Minimum bytes needed: magic(4) + class(1) + data(1) + version(1) + osabi(1)
# + padding(8) + type(2) + machine(2) = 20
_MIN_ELF_HEADER = 20

# How many bytes to read for language heuristic scanning.
# Large enough to catch section headers in most binaries, small enough to stay fast.
_LANG_SCAN_BYTES = 64 * 1024


def is_elf_binary(file_path: Path) -> bool:
    """Check if *file_path* is an ELF binary by reading the first 4 magic bytes.

    Returns ``False`` on any I/O error (missing file, permission denied, etc.).
    """
    try:
        with open(file_path, "rb") as fh:
            return fh.read(4) == _ELF_MAGIC
    except OSError:
        return False


def _read_elf_metadata(file_path: Path):
    """Read arch and OS/ABI from an ELF header.

    Returns (arch: str, os_abi: str) or raises ``ValueError`` on non-ELF /
    truncated files.
    """
    with open(file_path, "rb") as fh:
        header = fh.read(_MIN_ELF_HEADER)

    if len(header) < _MIN_ELF_HEADER or header[:4] != _ELF_MAGIC:
        raise ValueError(f"{file_path} is not a valid ELF binary")

    # OS/ABI byte at offset 7
    os_abi_byte = header[7]
    os_abi = _OSABI_MAP.get(os_abi_byte, "unknown")

    # e_machine: 2 bytes at offset 18, little-endian unsigned short
    (e_machine,) = struct.unpack_from("<H", header, 18)
    arch = _ARCH_MAP.get(e_machine, "unknown")

    return arch, os_abi


def _detect_source_language(file_path: Path) -> Optional[str]:
    """Heuristically detect the source language of a compiled binary.

    Reads the first chunk of the binary and looks for telltale strings
    embedded by the Rust and Go toolchains.  Returns ``None`` when the
    language cannot be determined.
    """
    try:
        with open(file_path, "rb") as fh:
            chunk = fh.read(_LANG_SCAN_BYTES)
    except OSError:
        return None

    # Rust: the compiler embeds `.rustc` section names and version strings
    if b".rustc" in chunk or b"rustc" in chunk:
        return "rust"

    # Go: the linker embeds `go.buildid` and runtime symbols
    if b"go.buildid" in chunk or b"runtime." in chunk:
        return "go"

    return None


def _detect_build_command(file_path: Path) -> Optional[str]:
    """Walk parent directories looking for known build-system files.

    Stops at the filesystem root.  Returns the conventional build command
    string for the first indicator found, or ``None``.
    """
    current = file_path.resolve().parent
    # Guard against infinite loops on unusual filesystems
    visited = set()
    while current not in visited:
        visited.add(current)
        for indicator_file, command in _BUILD_INDICATORS:
            if (current / indicator_file).is_file():
                return command
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def scan_binary(file_path: Path, required_by: str = "") -> Optional[BinaryDep]:
    """Scan a single file and return a ``BinaryDep`` if it is an ELF binary.

    Parameters
    ----------
    file_path:
        Path to the candidate binary file.
    required_by:
        Optional label (e.g. skill or hook name) that needs this binary.

    Returns ``None`` when the file is not an ELF binary or cannot be read.
    """
    file_path = Path(file_path)

    if not is_elf_binary(file_path):
        return None

    try:
        arch, os_abi = _read_elf_metadata(file_path)
    except (OSError, ValueError):
        return None

    source_lang = _detect_source_language(file_path)
    build_command = _detect_build_command(file_path)
    required_by_list = [required_by] if required_by else []

    return BinaryDep(
        name=file_path.name,
        path=str(file_path),
        arch=arch,
        os=os_abi,
        source_lang=source_lang,
        build_command=build_command,
        source_repo=None,
        required_by=required_by_list,
    )


def scan_binaries(
    file_paths: List[Path], required_by: str = ""
) -> List[BinaryDep]:
    """Scan multiple files and return ``BinaryDep`` instances for any ELF binaries found.

    Non-ELF files and unreadable files are silently skipped.
    """
    results: List[BinaryDep] = []
    for fp in file_paths:
        dep = scan_binary(Path(fp), required_by=required_by)
        if dep is not None:
            results.append(dep)
    return results
