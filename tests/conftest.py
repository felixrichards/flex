from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = TESTS_DIR / "resources"


def resource_path(*parts: str) -> Path:
    return RESOURCES_DIR.joinpath(*parts)
