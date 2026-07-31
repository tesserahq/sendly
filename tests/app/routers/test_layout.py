from uuid import uuid4
from fastapi import status


class TestLayoutRouter:
    def test_create_layout(self, client, setup_user):
        response = client.post(
            "/layouts",
            json={"alias": "My Layout", "html": "<html>${content}</html>"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["alias"] == "my-layout"
        assert data["html"] == "<html>${content}</html>"
        assert "id" in data
        assert data["created_by"]["id"] == str(setup_user.id)

    def test_create_layout_ignores_client_supplied_created_by_id(
        self, client, setup_user
    ):
        response = client.post(
            "/layouts",
            json={
                "alias": "Spoofed Layout",
                "html": "<html></html>",
                "created_by_id": str(uuid4()),
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["created_by"]["id"] == str(setup_user.id)

    def test_create_layout_slug_normalisation(self, client):
        response = client.post(
            "/layouts",
            json={"alias": "My Cool Layout!", "html": "<html>${content}</html>"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["alias"] == "my-cool-layout"

    def test_get_layout(self, client, setup_layout):
        response = client.get(f"/layouts/{setup_layout.id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == str(setup_layout.id)

    def test_get_layout_not_found(self, client):
        response = client.get(f"/layouts/{uuid4()}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_layouts(self, client, setup_layout):
        response = client.get("/layouts")
        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(setup_layout.id) in ids

    def test_update_layout(self, client, setup_layout):
        response = client.patch(
            f"/layouts/{setup_layout.id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "Updated Name"

    def test_update_layout_not_found(self, client):
        response = client.patch(f"/layouts/{uuid4()}", json={"name": "X"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_layout(self, client, setup_layout):
        response = client.delete(f"/layouts/{setup_layout.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        get_response = client.get(f"/layouts/{setup_layout.id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
