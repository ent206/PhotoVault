import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)

@pytest.fixture
def mock_library_dir(tmp_dir):
    """Creates a minimal mock DCIM structure for tests."""
    dcim = tmp_dir / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    yield tmp_dir
