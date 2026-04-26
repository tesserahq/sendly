import pytest
from app.models.template import Template


@pytest.fixture(scope="function")
def setup_template(db, faker):
    template = Template(
        alias=faker.slug(),
        name=faker.word(),
        subject="Hello ${name}",
        html="<p>Hello ${name}</p>",
        from_email=faker.email(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@pytest.fixture(scope="function")
def setup_template_with_layout(db, faker, setup_layout):
    template = Template(
        alias=faker.slug(),
        name=faker.word(),
        subject="Hello ${name}",
        html="<p>Hello ${name}</p>",
        from_email=faker.email(),
        layout_id=setup_layout.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template
