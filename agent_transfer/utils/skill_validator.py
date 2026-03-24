"""Skill dependency validator.

Checks if skill dependencies (Python packages) are available on the target system.
"""

import subprocess
import sys
import re
import tarfile
import tempfile
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Any, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


@dataclass
class SkillDependencyReport:
    """Dependency validation report for a skill."""
    skill_name: str
    skill_path: str
    skill_type: str  # user or project

    # Dependency file status
    has_requirements_txt: bool = False
    has_pyproject_toml: bool = False
    has_uv_lock: bool = False

    # Parsed dependencies
    requirements: List[str] = field(default_factory=list)
    pyproject_deps: List[str] = field(default_factory=list)

    # Validation results
    installed_packages: List[str] = field(default_factory=list)
    missing_packages: List[str] = field(default_factory=list)
    unknown_packages: List[str] = field(default_factory=list)  # Could not determine

    # Environment info
    has_uv: bool = False
    has_venv: bool = False
    venv_path: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if all dependencies are satisfied."""
        return len(self.missing_packages) == 0

    @property
    def has_dependencies(self) -> bool:
        """Check if skill has any dependency files."""
        return self.has_requirements_txt or self.has_pyproject_toml

    @property
    def dependency_score(self) -> float:
        """Calculate dependency satisfaction score (0-100)."""
        total = len(self.installed_packages) + len(self.missing_packages)
        if total == 0:
            return 100.0
        return (len(self.installed_packages) / total) * 100


def check_uv_available() -> bool:
    """Check if uv is available on the system."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_package_installed(package_name: str) -> bool:
    """Check if a Python package is installed.

    Args:
        package_name: Name of the package (without version specifier)

    Returns:
        True if installed, False otherwise
    """
    # Strip version specifiers
    clean_name = re.split(r'[<>=!~\[\]]', package_name)[0].strip()

    if not clean_name:
        return True  # Empty package name, skip

    try:
        # Try pip show first (works for most packages)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", clean_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def parse_requirements_txt(requirements_path: Path) -> List[str]:
    """Parse requirements.txt and extract package names.

    Args:
        requirements_path: Path to requirements.txt

    Returns:
        List of package specifications
    """
    packages = []
    try:
        content = requirements_path.read_text(encoding='utf-8')
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Skip -r includes and other flags
            if line.startswith('-'):
                continue
            # Skip editable installs
            if line.startswith('git+') or line.startswith('http'):
                continue
            packages.append(line)
    except (IOError, UnicodeDecodeError):
        pass
    return packages


def parse_pyproject_toml(pyproject_path: Path) -> List[str]:
    """Parse pyproject.toml and extract dependencies.

    Args:
        pyproject_path: Path to pyproject.toml

    Returns:
        List of package specifications
    """
    packages = []
    try:
        content = pyproject_path.read_text(encoding='utf-8')

        # Simple TOML parsing for dependencies
        # Look for [project] dependencies = [...] or [tool.uv] dependencies
        in_dependencies = False
        bracket_depth = 0

        for line in content.splitlines():
            stripped = line.strip()

            # Check for dependencies array start
            if 'dependencies' in stripped and '=' in stripped:
                in_dependencies = True
                # Check if it's a single-line array
                if '[' in stripped and ']' in stripped:
                    # Extract inline array
                    match = re.search(r'\[([^\]]*)\]', stripped)
                    if match:
                        deps_str = match.group(1)
                        for dep in deps_str.split(','):
                            dep = dep.strip().strip('"\'')
                            if dep:
                                packages.append(dep)
                    in_dependencies = False
                elif '[' in stripped:
                    bracket_depth = 1
                continue

            if in_dependencies:
                if '[' in stripped:
                    bracket_depth += 1
                if ']' in stripped:
                    bracket_depth -= 1
                    if bracket_depth <= 0:
                        in_dependencies = False
                        continue

                # Extract package from line
                dep = stripped.strip(',"\'[] ')
                if dep and not dep.startswith('#'):
                    packages.append(dep)

    except (IOError, UnicodeDecodeError):
        pass
    return packages


def check_skill_venv(skill_path: Path) -> Optional[Path]:
    """Check if skill has its own virtual environment.

    Args:
        skill_path: Path to skill directory

    Returns:
        Path to venv if found, None otherwise
    """
    venv_names = ['venv', '.venv', 'env', '.env']
    for name in venv_names:
        venv_path = skill_path / name
        if venv_path.is_dir() and (venv_path / 'bin' / 'python').exists():
            return venv_path
        # Windows check
        if venv_path.is_dir() and (venv_path / 'Scripts' / 'python.exe').exists():
            return venv_path
    return None


def validate_skill_dependencies(skill_path: Path, skill_type: str = "unknown") -> SkillDependencyReport:
    """Validate dependencies for a single skill.

    Args:
        skill_path: Path to skill directory
        skill_type: Type of skill (user/project)

    Returns:
        SkillDependencyReport with validation results
    """
    skill_name = skill_path.name

    report = SkillDependencyReport(
        skill_name=skill_name,
        skill_path=str(skill_path),
        skill_type=skill_type
    )

    # Check dependency files
    requirements_path = skill_path / "requirements.txt"
    pyproject_path = skill_path / "pyproject.toml"
    uv_lock_path = skill_path / "uv.lock"

    report.has_requirements_txt = requirements_path.exists()
    report.has_pyproject_toml = pyproject_path.exists()
    report.has_uv_lock = uv_lock_path.exists()

    # Check for uv availability
    report.has_uv = check_uv_available()

    # Check for skill-local venv
    venv_path = check_skill_venv(skill_path)
    if venv_path:
        report.has_venv = True
        report.venv_path = str(venv_path)

    # Parse dependencies
    all_deps: Set[str] = set()

    if report.has_requirements_txt:
        report.requirements = parse_requirements_txt(requirements_path)
        all_deps.update(report.requirements)

    if report.has_pyproject_toml:
        report.pyproject_deps = parse_pyproject_toml(pyproject_path)
        all_deps.update(report.pyproject_deps)

    # Check each dependency
    for dep in all_deps:
        # Extract package name (without version)
        pkg_name = re.split(r'[<>=!~\[\]]', dep)[0].strip()
        if not pkg_name:
            continue

        if check_package_installed(pkg_name):
            report.installed_packages.append(dep)
        else:
            report.missing_packages.append(dep)

    return report


def validate_all_skills(skills: List[Any]) -> List[SkillDependencyReport]:
    """Validate dependencies for all skills.

    Args:
        skills: List of Skill objects

    Returns:
        List of SkillDependencyReport objects
    """
    reports = []

    for skill in skills:
        skill_path = Path(skill.skill_path)
        if skill_path.exists() and skill_path.is_dir():
            report = validate_skill_dependencies(skill_path, skill.skill_type)
            reports.append(report)

    return reports


def display_skill_validation_report(reports: List[SkillDependencyReport]) -> None:
    """Display skill dependency validation report using Rich.

    Args:
        reports: List of SkillDependencyReport objects
    """
    if not reports:
        console.print("[yellow]No skills found to validate.[/yellow]")
        return

    # Check uv availability once
    has_uv = check_uv_available()

    # Summary counts
    total = len(reports)
    with_deps = sum(1 for r in reports if r.has_dependencies)
    valid = sum(1 for r in reports if r.is_valid)
    missing_deps = sum(1 for r in reports if not r.is_valid and r.has_dependencies)
    no_deps = total - with_deps

    # Summary panel
    summary_text = (
        f"[bold]Skill Dependency Validation[/bold]\n\n"
        f"Total Skills: {total}\n"
        f"[dim]No dependencies defined: {no_deps}[/dim]\n"
        f"With dependencies: {with_deps}\n"
        f"  [green]All satisfied: {valid}[/green]\n"
        f"  [red]Missing packages: {missing_deps}[/red]\n\n"
        f"[cyan]uv available:[/cyan] {'Yes ✓' if has_uv else 'No ✗'}"
    )

    console.print(Panel(summary_text, title="Summary", box=box.ROUNDED))

    # Skills with dependencies table
    skills_with_deps = [r for r in reports if r.has_dependencies]

    if skills_with_deps:
        console.print("\n")
        table = Table(title="Skills with Dependencies", box=box.ROUNDED)
        table.add_column("Skill", style="cyan")
        table.add_column("Type", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Deps", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Missing", style="red")

        for report in skills_with_deps:
            type_badge = "[green]USER[/green]" if report.skill_type == "user" else "[blue]PROJECT[/blue]"

            # Dependency indicators
            deps_parts = []
            if report.has_requirements_txt:
                deps_parts.append("req")
            if report.has_pyproject_toml:
                deps_parts.append("pyp")
            if report.has_uv_lock:
                deps_parts.append("uv")
            deps_str = ", ".join(deps_parts)

            # Score
            score = f"{report.dependency_score:.0f}%"
            score_style = "green" if report.dependency_score == 100 else "yellow" if report.dependency_score >= 50 else "red"

            # Status
            if report.is_valid:
                status = "[green]✓ OK[/green]"
            else:
                status = "[red]✗ Missing[/red]"

            # Missing packages (truncated)
            missing = ", ".join(report.missing_packages[:3])
            if len(report.missing_packages) > 3:
                missing += f" (+{len(report.missing_packages) - 3})"

            table.add_row(
                report.skill_name,
                type_badge,
                f"[{score_style}]{score}[/{score_style}]",
                deps_str,
                status,
                missing or "-"
            )

        console.print(table)

    # Skills without dependencies
    skills_no_deps = [r for r in reports if not r.has_dependencies]
    if skills_no_deps:
        console.print(f"\n[dim]Skills without dependency files: {len(skills_no_deps)}[/dim]")
        names = ", ".join(r.skill_name for r in skills_no_deps[:5])
        if len(skills_no_deps) > 5:
            names += f" (+{len(skills_no_deps) - 5} more)"
        console.print(f"[dim]  {names}[/dim]")

    # Recommendations
    issues = [r for r in reports if not r.is_valid and r.has_dependencies]
    if issues:
        console.print("\n[bold yellow]Recommendations:[/bold yellow]")

        # Collect all missing packages
        all_missing = set()
        for report in issues:
            for pkg in report.missing_packages:
                pkg_name = re.split(r'[<>=!~\[\]]', pkg)[0].strip()
                all_missing.add(pkg_name)

        if has_uv:
            console.print("\n[cyan]Using uv (recommended):[/cyan]")
            for report in issues:
                if report.has_uv_lock:
                    console.print(f"  cd {report.skill_path} && uv sync")
                elif report.has_pyproject_toml:
                    console.print(f"  cd {report.skill_path} && uv pip install -e .")
                elif report.has_requirements_txt:
                    console.print(f"  cd {report.skill_path} && uv pip install -r requirements.txt")
        else:
            console.print("\n[cyan]Using pip:[/cyan]")
            for report in issues:
                if report.has_pyproject_toml:
                    console.print(f"  cd {report.skill_path} && pip install -e .")
                elif report.has_requirements_txt:
                    console.print(f"  cd {report.skill_path} && pip install -r requirements.txt")

            console.print("\n[dim]Tip: Install uv for faster, isolated dependency management:[/dim]")
            console.print("[dim]  curl -LsSf https://astral.sh/uv/install.sh | sh[/dim]")
    else:
        console.print("\n[green]✓ All skill dependencies are satisfied![/green]")


def get_skills_with_missing_deps(reports: List[SkillDependencyReport]) -> List[SkillDependencyReport]:
    """Get list of skills with missing dependencies.

    Args:
        reports: List of SkillDependencyReport objects

    Returns:
        List of reports with missing dependencies
    """
    return [r for r in reports if not r.is_valid and r.has_dependencies]


# =============================================================================
# Environment Detection and Setup Helpers
# =============================================================================

@dataclass
class EnvironmentInfo:
    """Information about the Python environment."""
    python_version: str
    python_path: str
    pip_version: Optional[str] = None
    has_uv: bool = False
    uv_version: Optional[str] = None
    active_venv: Optional[str] = None
    is_in_venv: bool = False
    global_site_packages: bool = False


def detect_environment() -> EnvironmentInfo:
    """Detect the current Python environment configuration.

    Returns:
        EnvironmentInfo with details about the current environment
    """
    info = EnvironmentInfo(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        python_path=sys.executable
    )

    # Check if we're in a venv
    info.is_in_venv = (
        hasattr(sys, 'real_prefix') or  # virtualenv
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)  # venv
    )

    if info.is_in_venv:
        info.active_venv = sys.prefix

    # Get pip version
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Output: "pip X.Y.Z from ..."
            match = re.search(r'pip (\d+\.\d+(?:\.\d+)?)', result.stdout)
            if match:
                info.pip_version = match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Check for uv
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            info.has_uv = True
            # Output: "uv X.Y.Z"
            match = re.search(r'uv (\d+\.\d+(?:\.\d+)?)', result.stdout)
            if match:
                info.uv_version = match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return info


def display_environment_info(info: EnvironmentInfo) -> None:
    """Display environment information using Rich.

    Args:
        info: EnvironmentInfo object
    """
    # Environment status
    venv_status = (
        f"[green]Active: {info.active_venv}[/green]"
        if info.is_in_venv
        else "[yellow]Not in a virtual environment[/yellow]"
    )

    uv_status = (
        f"[green]Installed (v{info.uv_version})[/green]"
        if info.has_uv
        else "[yellow]Not installed[/yellow]"
    )

    env_text = (
        f"[bold]Python Environment[/bold]\n\n"
        f"Python: {info.python_version}\n"
        f"Path: [dim]{info.python_path}[/dim]\n"
        f"pip: {info.pip_version or 'Not found'}\n\n"
        f"[bold]Virtual Environment[/bold]\n"
        f"{venv_status}\n\n"
        f"[bold]uv Package Manager[/bold]\n"
        f"{uv_status}"
    )

    console.print(Panel(env_text, title="Environment Status", box=box.ROUNDED))


def get_setup_recommendations(
    info: EnvironmentInfo,
    reports: List[SkillDependencyReport]
) -> List[Tuple[str, str]]:
    """Get setup recommendations based on environment and validation results.

    Args:
        info: EnvironmentInfo from detect_environment()
        reports: List of SkillDependencyReport objects

    Returns:
        List of (recommendation, command) tuples
    """
    recommendations = []

    # Check if uv needs to be installed
    if not info.has_uv:
        recommendations.append((
            "Install uv for faster, isolated dependency management",
            "curl -LsSf https://astral.sh/uv/install.sh | sh"
        ))

    # Check for skills with missing dependencies
    missing_deps_skills = get_skills_with_missing_deps(reports)

    if missing_deps_skills:
        for report in missing_deps_skills:
            skill_path = report.skill_path

            # Recommend based on what dependency files exist
            if report.has_uv_lock and info.has_uv:
                recommendations.append((
                    f"Install dependencies for '{report.skill_name}' using uv sync",
                    f"cd {skill_path} && uv sync"
                ))
            elif report.has_pyproject_toml:
                if info.has_uv:
                    recommendations.append((
                        f"Install dependencies for '{report.skill_name}'",
                        f"cd {skill_path} && uv pip install -e ."
                    ))
                else:
                    recommendations.append((
                        f"Install dependencies for '{report.skill_name}'",
                        f"cd {skill_path} && pip install -e ."
                    ))
            elif report.has_requirements_txt:
                if info.has_uv:
                    recommendations.append((
                        f"Install dependencies for '{report.skill_name}'",
                        f"cd {skill_path} && uv pip install -r requirements.txt"
                    ))
                else:
                    recommendations.append((
                        f"Install dependencies for '{report.skill_name}'",
                        f"cd {skill_path} && pip install -r requirements.txt"
                    ))

    # If not in a venv, recommend creating one
    if not info.is_in_venv and missing_deps_skills:
        if info.has_uv:
            recommendations.insert(0, (
                "Create a virtual environment (recommended before installing)",
                "uv venv && source .venv/bin/activate"
            ))
        else:
            recommendations.insert(0, (
                "Create a virtual environment (recommended before installing)",
                "python -m venv .venv && source .venv/bin/activate"
            ))

    return recommendations


def display_setup_recommendations(recommendations: List[Tuple[str, str]]) -> None:
    """Display setup recommendations using Rich.

    Args:
        recommendations: List of (recommendation, command) tuples
    """
    if not recommendations:
        console.print("\n[green]✓ No setup actions needed![/green]")
        return

    console.print("\n[bold cyan]Recommended Setup Actions:[/bold cyan]\n")

    for i, (desc, cmd) in enumerate(recommendations, 1):
        console.print(f"[bold]{i}.[/bold] {desc}")
        console.print(f"   [dim]$[/dim] [cyan]{cmd}[/cyan]\n")


# =============================================================================
# Archive Validation
# =============================================================================

def extract_skills_from_archive(archive_path: Path) -> Tuple[Path, List[Path]]:
    """Extract skills from a tar.gz archive to a temp directory.

    Args:
        archive_path: Path to the tar.gz archive

    Returns:
        Tuple of (temp_dir, list of skill directories)
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="agent_transfer_validate_"))

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(temp_dir)
    except (tarfile.TarError, IOError) as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"Failed to extract archive: {e}")

    # Find skill directories (directories containing SKILL.md)
    skill_dirs = []

    # Look for skills/ directory structure
    for skills_dir in temp_dir.rglob("skills"):
        if skills_dir.is_dir():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    skill_dirs.append(skill_dir)

    # Also check root level for SKILL.md files
    for skill_md in temp_dir.rglob("SKILL.md"):
        skill_dir = skill_md.parent
        if skill_dir not in skill_dirs:
            skill_dirs.append(skill_dir)

    return temp_dir, skill_dirs


def validate_archive_skills(archive_path: Path) -> Tuple[List[SkillDependencyReport], Path]:
    """Validate skill dependencies from an archive without importing.

    Args:
        archive_path: Path to the tar.gz archive

    Returns:
        Tuple of (list of SkillDependencyReport, temp_dir for cleanup)
    """
    archive_path = Path(archive_path)

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    if not archive_path.suffix == '.gz' or not str(archive_path).endswith('.tar.gz'):
        raise ValueError("Archive must be a .tar.gz file")

    temp_dir, skill_dirs = extract_skills_from_archive(archive_path)

    reports = []
    for skill_dir in skill_dirs:
        # Determine skill type from path structure
        skill_type = "archive"
        if "user" in str(skill_dir).lower():
            skill_type = "user"
        elif "project" in str(skill_dir).lower():
            skill_type = "project"

        report = validate_skill_dependencies(skill_dir, skill_type)
        reports.append(report)

    return reports, temp_dir


def display_archive_validation_report(
    reports: List[SkillDependencyReport],
    archive_path: Path
) -> None:
    """Display validation report for skills from an archive.

    Args:
        reports: List of SkillDependencyReport objects
        archive_path: Path to the archive that was validated
    """
    if not reports:
        console.print("[yellow]No skills found in archive.[/yellow]")
        return

    # Check uv availability once
    has_uv = check_uv_available()

    # Summary counts
    total = len(reports)
    with_deps = sum(1 for r in reports if r.has_dependencies)
    valid = sum(1 for r in reports if r.is_valid)
    missing_deps = sum(1 for r in reports if not r.is_valid and r.has_dependencies)
    no_deps = total - with_deps

    # Collect all missing packages
    all_missing = set()
    for report in reports:
        for pkg in report.missing_packages:
            pkg_name = re.split(r'[<>=!~\[\]]', pkg)[0].strip()
            all_missing.add(pkg_name)

    # Summary panel
    summary_text = (
        f"[bold]Archive Pre-Import Validation[/bold]\n\n"
        f"Archive: [dim]{archive_path}[/dim]\n\n"
        f"Total Skills: {total}\n"
        f"[dim]No dependencies defined: {no_deps}[/dim]\n"
        f"With dependencies: {with_deps}\n"
        f"  [green]All satisfied: {valid}[/green]\n"
        f"  [red]Missing packages: {missing_deps}[/red]\n\n"
        f"[cyan]uv available:[/cyan] {'Yes ✓' if has_uv else 'No ✗'}"
    )

    if all_missing:
        summary_text += f"\n\n[bold red]Missing packages:[/bold red] {', '.join(sorted(all_missing))}"

    console.print(Panel(summary_text, title="Archive Validation Summary", box=box.ROUNDED))

    # Skills table
    skills_with_deps = [r for r in reports if r.has_dependencies]

    if skills_with_deps:
        console.print("\n")
        table = Table(title="Skills with Dependencies", box=box.ROUNDED)
        table.add_column("Skill", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Deps", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Missing", style="red")

        for report in skills_with_deps:
            # Dependency indicators
            deps_parts = []
            if report.has_requirements_txt:
                deps_parts.append("req")
            if report.has_pyproject_toml:
                deps_parts.append("pyp")
            if report.has_uv_lock:
                deps_parts.append("uv")
            deps_str = ", ".join(deps_parts)

            # Score
            score = f"{report.dependency_score:.0f}%"
            score_style = "green" if report.dependency_score == 100 else "yellow" if report.dependency_score >= 50 else "red"

            # Status
            if report.is_valid:
                status = "[green]✓ OK[/green]"
            else:
                status = "[red]✗ Missing[/red]"

            # Missing packages (truncated)
            missing = ", ".join(report.missing_packages[:3])
            if len(report.missing_packages) > 3:
                missing += f" (+{len(report.missing_packages) - 3})"

            table.add_row(
                report.skill_name,
                f"[{score_style}]{score}[/{score_style}]",
                deps_str,
                status,
                missing or "-"
            )

        console.print(table)

    # Import readiness
    if missing_deps == 0:
        console.print("\n[green]✓ All skill dependencies are satisfied. Safe to import![/green]")
    else:
        console.print("\n[yellow]⚠ Some skills have missing dependencies.[/yellow]")
        console.print("[dim]You can still import, but skills may not work correctly.[/dim]")

        # Show install commands
        console.print("\n[bold]Install missing packages before or after import:[/bold]")
        if has_uv:
            console.print(f"  [cyan]uv pip install {' '.join(sorted(all_missing))}[/cyan]")
        else:
            console.print(f"  [cyan]pip install {' '.join(sorted(all_missing))}[/cyan]")


# =============================================================================
# Comprehensive Readiness Check
# =============================================================================

@dataclass
class ReadinessReport:
    """Comprehensive system readiness report for skill transfer."""
    # Environment info
    environment: EnvironmentInfo = None

    # Skill validation results
    skill_reports: List[SkillDependencyReport] = field(default_factory=list)
    archive_path: Optional[str] = None
    is_archive_check: bool = False

    # Summary metrics
    total_skills: int = 0
    skills_with_deps: int = 0
    skills_satisfied: int = 0
    skills_missing_deps: int = 0

    # Collected issues
    all_missing_packages: Set[str] = field(default_factory=set)

    # Readiness status
    is_ready: bool = True
    readiness_issues: List[str] = field(default_factory=list)

    # Setup recommendations
    recommendations: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def readiness_score(self) -> float:
        """Calculate overall readiness score (0-100)."""
        if self.total_skills == 0:
            return 100.0 if self.environment and self.environment.has_uv else 80.0

        score = 0.0

        # Environment score (30 points)
        if self.environment:
            if self.environment.pip_version:
                score += 10
            if self.environment.has_uv:
                score += 15
            if self.environment.is_in_venv:
                score += 5

        # Dependency satisfaction score (70 points)
        if self.total_skills > 0:
            satisfaction_rate = self.skills_satisfied / self.total_skills
            score += satisfaction_rate * 70
        else:
            score += 70  # No skills = no dependency issues

        return min(score, 100.0)

    @property
    def status_emoji(self) -> str:
        """Get status emoji based on readiness."""
        score = self.readiness_score
        if score >= 90:
            return "✅"
        elif score >= 70:
            return "⚠️"
        elif score >= 50:
            return "🔶"
        else:
            return "❌"


def check_system_readiness(
    archive_path: Optional[Path] = None,
    local_skills: Optional[List[Any]] = None
) -> Tuple[ReadinessReport, Optional[Path]]:
    """Perform comprehensive system readiness check.

    This is the main entry point for the check-ready command.
    Checks environment, validates skills (local or from archive),
    and generates recommendations.

    Args:
        archive_path: Optional path to archive to validate (pre-import check)
        local_skills: Optional list of local Skill objects (if no archive)

    Returns:
        Tuple of (ReadinessReport, temp_dir for cleanup if archive was used)
    """
    report = ReadinessReport()
    temp_dir = None

    # Step 1: Detect environment
    report.environment = detect_environment()

    # Step 2: Check for basic issues
    if not report.environment.pip_version:
        report.readiness_issues.append("pip not found - cannot install packages")
        report.is_ready = False

    # Step 3: Validate skills
    if archive_path:
        # Archive validation (pre-import)
        report.is_archive_check = True
        report.archive_path = str(archive_path)

        try:
            skill_reports, temp_dir = validate_archive_skills(archive_path)
            report.skill_reports = skill_reports
        except (FileNotFoundError, ValueError) as e:
            report.readiness_issues.append(f"Archive error: {e}")
            report.is_ready = False
            return report, None
    elif local_skills:
        # Local skills validation
        report.skill_reports = validate_all_skills(local_skills)

    # Step 4: Calculate metrics
    report.total_skills = len(report.skill_reports)
    report.skills_with_deps = sum(1 for r in report.skill_reports if r.has_dependencies)
    report.skills_satisfied = sum(1 for r in report.skill_reports if r.is_valid)
    report.skills_missing_deps = sum(
        1 for r in report.skill_reports
        if not r.is_valid and r.has_dependencies
    )

    # Step 5: Collect all missing packages
    for skill_report in report.skill_reports:
        for pkg in skill_report.missing_packages:
            pkg_name = re.split(r'[<>=!~\[\]]', pkg)[0].strip()
            report.all_missing_packages.add(pkg_name)

    # Step 6: Determine readiness
    if report.skills_missing_deps > 0:
        report.readiness_issues.append(
            f"{report.skills_missing_deps} skill(s) have missing dependencies"
        )

    if not report.environment.has_uv:
        report.readiness_issues.append(
            "uv not installed - recommended for isolated dependency management"
        )

    if not report.environment.is_in_venv and report.skills_missing_deps > 0:
        report.readiness_issues.append(
            "Not in a virtual environment - recommended before installing packages"
        )

    # Step 7: Generate recommendations
    report.recommendations = get_setup_recommendations(
        report.environment,
        report.skill_reports
    )

    # Final readiness determination
    report.is_ready = (
        report.skills_missing_deps == 0 and
        report.environment.pip_version is not None
    )

    return report, temp_dir


def display_readiness_report(
    report: ReadinessReport,
    verbose: bool = False,
    show_all_skills: bool = False
) -> None:
    """Display comprehensive readiness report using Rich.

    Args:
        report: ReadinessReport from check_system_readiness()
        verbose: Show detailed information
        show_all_skills: Show all skills, not just those with issues
    """
    # Header with overall status
    score = report.readiness_score
    status_color = "green" if score >= 90 else "yellow" if score >= 70 else "red"

    header_text = (
        f"[bold]System Readiness Check[/bold] {report.status_emoji}\n\n"
        f"Readiness Score: [{status_color}]{score:.0f}%[/{status_color}]\n"
    )

    if report.is_archive_check:
        header_text += f"Archive: [dim]{report.archive_path}[/dim]\n"

    header_text += f"Total Skills: {report.total_skills}\n"

    if report.skills_with_deps > 0:
        header_text += (
            f"  Dependencies satisfied: [green]{report.skills_satisfied}[/green] / "
            f"[yellow]{report.skills_with_deps}[/yellow]\n"
        )

    # Overall verdict
    if report.is_ready:
        header_text += "\n[bold green]✓ READY[/bold green] - System can handle these skills"
    else:
        header_text += "\n[bold yellow]⚠ ACTION NEEDED[/bold yellow] - See recommendations below"

    console.print(Panel(header_text, title="Readiness Summary", box=box.DOUBLE))

    # Environment section
    if report.environment:
        env = report.environment
        env_items = []

        # Python
        env_items.append(f"Python {env.python_version}")

        # pip
        if env.pip_version:
            env_items.append(f"[green]pip {env.pip_version}[/green]")
        else:
            env_items.append("[red]pip not found[/red]")

        # uv
        if env.has_uv:
            env_items.append(f"[green]uv {env.uv_version}[/green]")
        else:
            env_items.append("[dim]uv not installed[/dim]")

        # venv
        if env.is_in_venv:
            env_items.append("[green]venv active[/green]")
        else:
            env_items.append("[dim]no venv[/dim]")

        console.print(f"\n[bold]Environment:[/bold] {' │ '.join(env_items)}")

    # Issues section
    if report.readiness_issues:
        console.print("\n[bold yellow]Issues Found:[/bold yellow]")
        for issue in report.readiness_issues:
            console.print(f"  [yellow]•[/yellow] {issue}")

    # Missing packages summary
    if report.all_missing_packages:
        console.print(f"\n[bold red]Missing Packages:[/bold red] {', '.join(sorted(report.all_missing_packages))}")

    # Skills with issues table
    skills_with_issues = [r for r in report.skill_reports if not r.is_valid and r.has_dependencies]

    if skills_with_issues or (show_all_skills and report.skill_reports):
        console.print("\n")

        skills_to_show = report.skill_reports if show_all_skills else skills_with_issues
        table_title = "All Skills" if show_all_skills else "Skills Requiring Action"

        table = Table(title=table_title, box=box.ROUNDED)
        table.add_column("Skill", style="cyan")
        table.add_column("Type", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Missing", style="red")

        for skill_report in skills_to_show:
            type_str = skill_report.skill_type.upper()[:4]

            if skill_report.is_valid:
                status = "[green]✓ Ready[/green]"
            elif not skill_report.has_dependencies:
                status = "[dim]No deps[/dim]"
            else:
                status = "[red]✗ Missing[/red]"

            missing = ", ".join(skill_report.missing_packages[:2])
            if len(skill_report.missing_packages) > 2:
                missing += f" (+{len(skill_report.missing_packages) - 2})"

            table.add_row(
                skill_report.skill_name,
                type_str,
                status,
                missing or "-"
            )

        console.print(table)

    # Recommendations section
    if report.recommendations:
        console.print("\n[bold cyan]━━━ Recommended Actions ━━━[/bold cyan]\n")

        for i, (desc, cmd) in enumerate(report.recommendations, 1):
            console.print(f"[bold]{i}.[/bold] {desc}")
            console.print(f"   [dim]$[/dim] [green]{cmd}[/green]\n")

        # Quick fix suggestion
        if report.all_missing_packages and report.environment and report.environment.has_uv:
            pkgs = ' '.join(sorted(report.all_missing_packages))
            console.print("[bold]Quick Fix (install all missing):[/bold]")
            console.print(f"   [dim]$[/dim] [green]uv pip install {pkgs}[/green]\n")
        elif report.all_missing_packages:
            pkgs = ' '.join(sorted(report.all_missing_packages))
            console.print("[bold]Quick Fix (install all missing):[/bold]")
            console.print(f"   [dim]$[/dim] [green]pip install {pkgs}[/green]\n")

    # Final message
    if report.is_ready:
        if report.is_archive_check:
            console.print("[green]✓ Ready to import! Run:[/green]")
            console.print(f"   [dim]$[/dim] [cyan]agent-transfer import {report.archive_path}[/cyan]")
        else:
            console.print("[green]✓ All skills are ready to use![/green]")
    else:
        console.print("[yellow]Complete the recommended actions above, then re-run this check.[/yellow]")
