"""UAT-specific pytest configuration."""
import pytest

# UAT tests use the same DB setup as unit tests
# but are always marked as integration tests
def pytest_collection_modifyitems(items):
    for item in items:
        if 'uat' in str(item.fspath):
            item.add_marker(pytest.mark.integration)
