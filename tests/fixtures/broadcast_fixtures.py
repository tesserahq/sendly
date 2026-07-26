import pytest


@pytest.fixture(scope="function")
def project_id(faker):
    """A project UUID to scope broadcast/suppression tests."""
    return faker.uuid4(cast_to=None)
