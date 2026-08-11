"""The package version must match pyproject.toml.

Two sources of truth for one number drift silently: `pip show` reports one value
while `payrexx.__version__` claims another, and a consumer pinning on the latter
believes it has features it does not. Caught in the field: the library shipped as
0.2.0 while still reporting 0.1.0.
"""

from __future__ import annotations

import pathlib
import re

import payrexx

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_dunder_version_matches_pyproject():
    match = re.search(r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert match, "no version found in pyproject.toml"
    assert payrexx.__version__ == match.group(1), (
        f"payrexx.__version__ is {payrexx.__version__} but pyproject.toml says "
        f"{match.group(1)} — bump both."
    )


def test_installed_metadata_matches_too():
    """Guards against a stale editable install serving an old version."""
    from importlib.metadata import version

    assert version("payrexx") == payrexx.__version__
