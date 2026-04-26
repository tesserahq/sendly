import pytest
from app.models.layout import Layout


@pytest.fixture(scope="function")
def setup_layout(db, faker):
    layout = Layout(
        alias=faker.slug(),
        name=faker.word(),
        html="<html><body>${content}</body></html>",
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout
