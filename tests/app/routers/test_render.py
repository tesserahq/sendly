from uuid import uuid4

from fastapi import status

from app.models.email import Email
from app.repositories.layout_repository import LayoutRepository


class TestRenderRouter:
    def test_renders_body_in_layout_and_subject(self, client, setup_layout):
        response = client.post(
            "/render",
            json={
                "html": "<p>Hi ${first_name}</p>",
                "subject": "Hello ${first_name}",
                "layout_id": str(setup_layout.id),
                "template_variables": {"first_name": "Alice"},
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "html": "<html><body><p>Hi Alice</p></body></html>",
            "subject": "Hello Alice",
        }

    def test_renders_by_layout_alias(self, client, setup_layout):
        response = client.post(
            "/render",
            json={"html": "<p>hi</p>", "layout_alias": setup_layout.alias},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["html"] == "<html><body><p>hi</p></body></html>"

    def test_without_layout_renders_body_only(self, client):
        response = client.post("/render", json={"html": "<p>${year}</p>"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["html"].startswith("<p>20")
        assert response.json()["subject"] == ""

    def test_missing_variable_is_422_and_named(self, client):
        response = client.post(
            "/render",
            json={"html": "<p>Hi ${first_name}</p>", "subject": "Hello"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "first_name" in response.json()["detail"]

    def test_syntax_error_is_422(self, client):
        response = client.post("/render", json={"html": "<p>${</p>"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_unknown_layout_is_404(self, client):
        response = client.post(
            "/render", json={"html": "<p>hi</p>", "layout_id": str(uuid4())}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_soft_deleted_layout_is_404(self, client, db, setup_layout):
        LayoutRepository(db).delete_layout(setup_layout.id)

        response = client.post(
            "/render",
            json={"html": "<p>hi</p>", "layout_id": str(setup_layout.id)},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_has_no_side_effects(self, client, db, setup_layout):
        before = db.query(Email).count()

        client.post(
            "/render",
            json={"html": "<p>hi</p>", "layout_id": str(setup_layout.id)},
        )

        assert db.query(Email).count() == before
