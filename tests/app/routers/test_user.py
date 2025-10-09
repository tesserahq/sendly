def test_list_users(client):
    """Test GET /users endpoint."""
    response = client.get("/users")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)


def test_create_user(client):
    """Test POST /users endpoint."""
    response = client.post(
        "/users",
        json={"first_name": "Test", "last_name": "User", "email": "test@example.com"},
    )
    assert response.status_code == 201
    user = response.json()
    assert user["first_name"] == "Test"
    assert user["last_name"] == "User"
    assert user["email"] == "test@example.com"
