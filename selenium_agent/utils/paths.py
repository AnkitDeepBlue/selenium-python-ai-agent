"""
Path helpers for generated Selenium agent files.
"""

from pathlib import Path


def get_output_root(output_dir: str) -> Path:
    """Return the absolute root directory for generated files."""
    return Path(output_dir).resolve()


def resolve_input_path(file_path: str, output_dir: str) -> Path:
    """
    Resolve an input file path from either the current working directory or output_dir.

    This supports both:
    - generated_tests/tests/test_login.py
    - tests/test_login.py when output_dir is generated_tests
    """
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate.resolve()

    if candidate.exists():
        return candidate.resolve()

    output_root = get_output_root(output_dir)

    # Support caller-provided paths that already include the output_dir prefix.
    if candidate.parts and candidate.parts[0] == output_root.name:
        return (output_root.parent / candidate).resolve()

    return (output_root / candidate).resolve()


def safe_output_path(output_dir: str, filename: str) -> Path:
    """Resolve a model-provided filename and ensure it stays inside output_dir."""
    relative_path = Path(filename)
    if relative_path.is_absolute():
        raise ValueError(f"Refusing to write absolute path from model output: {filename}")

    output_root = get_output_root(output_dir)
    destination = (output_root / relative_path).resolve()

    try:
        destination.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside output_dir: {filename}") from exc

    return destination
