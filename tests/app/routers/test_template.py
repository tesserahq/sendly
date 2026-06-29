from uuid import uuid4
from fastapi import status
from unittest.mock import patch, MagicMock


class TestTemplateRouter:
    def test_create_template(self, client):
        response = client.post(
            "/templates",
            json={
                "alias": "Welcome Email",
                "subject": "Welcome ${name}",
                "html": "<p>Hello ${name}</p>",
                "from_email": "noreply@example.com",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["alias"] == "welcome-email"
        assert data["subject"] == "Welcome ${name}"
        assert "id" in data

    def test_create_template_slug_normalisation(self, client):
        response = client.post(
            "/templates",
            json={
                "alias": "My Cool Template!",
                "subject": "Hi",
                "html": "<p>hi</p>",
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["alias"] == "my-cool-template"

    def test_get_template(self, client, setup_template):
        response = client.get(f"/templates/{setup_template.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(setup_template.id)
        assert data["layout_id"] is None
        assert data["layout"] is None

    def test_get_template_with_layout(
        self, client, setup_template_with_layout, setup_layout
    ):
        response = client.get(f"/templates/{setup_template_with_layout.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["layout_id"] == str(setup_layout.id)
        assert data["layout"]["id"] == str(setup_layout.id)
        assert data["layout"]["alias"] == setup_layout.alias

    def test_get_template_not_found(self, client):
        response = client.get(f"/templates/{uuid4()}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_templates(self, client, setup_template):
        response = client.get("/templates")
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(setup_template.id) in ids

    def test_list_templates_includes_nested_layout(
        self, client, setup_template_with_layout, setup_layout
    ):
        response = client.get("/templates")
        assert response.status_code == status.HTTP_200_OK
        template = next(
            item
            for item in response.json()["items"]
            if item["id"] == str(setup_template_with_layout.id)
        )
        assert template["layout_id"] == str(setup_layout.id)
        assert template["layout"]["id"] == str(setup_layout.id)
        assert template["layout"]["alias"] == setup_layout.alias

    def test_update_template(self, client, setup_template):
        response = client.patch(
            f"/templates/{setup_template.id}",
            json={"subject": "New Subject"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["subject"] == "New Subject"

    def test_update_template_with_layout(self, client, setup_template, setup_layout):
        response = client.patch(
            f"/templates/{setup_template.id}",
            json={"layout_id": str(setup_layout.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["layout_id"] == str(setup_layout.id)
        assert data["layout"]["id"] == str(setup_layout.id)
        assert data["layout"]["alias"] == setup_layout.alias

    def test_delete_template(self, client, setup_template):
        response = client.delete(f"/templates/{setup_template.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        get_response = client.get(f"/templates/{setup_template.id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_send_email_with_template_alias(self, client, setup_template):
        mock_result = MagicMock(ok=True, provider_message_id="pm-123")
        with patch(
            "app.commands.send_email_command.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            mock_provider.return_value.send_email.return_value = mock_result

            response = client.post(
                "/emails",
                json={
                    "to": ["user@example.com"],
                    "template_alias": setup_template.alias,
                    "template_variables": {"name": "Alice"},
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["subject"] == "Hello Alice"
        assert "Hello Alice" in data["body"]

    def test_send_email_with_template_id(self, client, setup_template):
        mock_result = MagicMock(ok=True, provider_message_id="pm-456")
        with patch(
            "app.commands.send_email_command.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            mock_provider.return_value.send_email.return_value = mock_result

            response = client.post(
                "/emails",
                json={
                    "to": ["user@example.com"],
                    "template_id": str(setup_template.id),
                    "template_variables": {"name": "Bob"},
                },
            )

        assert response.status_code == status.HTTP_200_OK
        assert "Hello Bob" in response.json()["body"]

    def test_send_email_template_and_inline_html_rejected(self, client, setup_template):
        response = client.post(
            "/emails",
            json={
                "to": ["user@example.com"],
                "template_alias": setup_template.alias,
                "html": "<p>inline</p>",
                "from_email": "x@example.com",
                "subject": "Test",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_send_email_template_not_found(self, client):
        response = client.post(
            "/emails",
            json={
                "to": ["user@example.com"],
                "template_alias": "nonexistent-template",
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_send_email_template_missing_from_email(self, client, db):
        from app.models.template import Template

        template_no_from = Template(
            alias="no-from-template",
            subject="Hi ${name}",
            html="<p>${name}</p>",
        )
        db.add(template_no_from)
        db.commit()

        response = client.post(
            "/emails",
            json={
                "to": ["user@example.com"],
                "template_alias": "no-from-template",
                "template_variables": {"name": "Dave"},
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_send_email_with_layout(self, client, setup_template_with_layout):
        mock_result = MagicMock(ok=True, provider_message_id="pm-789")
        with patch(
            "app.commands.send_email_command.get_default_provider"
        ) as mock_provider:
            mock_provider.return_value.provider_id = "postmark"
            mock_provider.return_value.send_email.return_value = mock_result

            response = client.post(
                "/emails",
                json={
                    "to": ["user@example.com"],
                    "template_alias": setup_template_with_layout.alias,
                    "template_variables": {"name": "Carol"},
                },
            )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()["body"]
        assert "<html>" in body
        assert "Hello Carol" in body
