from uuid import uuid4
from fastapi import status


class TestEmailRouter:
    """Test suite for email router endpoints."""

    def test_get_email(self, client, setup_email):
        """Test getting an email by ID."""
        response = client.get(f"/emails/{setup_email.id}")

        assert response.status_code == status.HTTP_200_OK
        email_data = response.json()

        assert email_data["id"] == str(setup_email.id)
        assert email_data["from_email"] == setup_email.from_email
        assert email_data["to_email"] == setup_email.to_email
        assert email_data["subject"] == setup_email.subject
        assert email_data["status"] == setup_email.status
        assert email_data["project_id"] == setup_email.project_id
        assert email_data["provider"] == setup_email.provider

    def test_get_email_not_found(self, client):
        """Test getting a non-existent email returns 404."""
        non_existent_id = uuid4()
        response = client.get(f"/emails/{non_existent_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_list_emails_filters_by_batch_id(self, client, db, faker):
        from app.models.email import Email

        batch_id = str(uuid4())
        matching = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Broadcast",
            body="Body",
            status="queued",
            provider="postmark",
            batch_id=batch_id,
        )
        other = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Other",
            body="Body",
            status="queued",
            provider="postmark",
            batch_id=str(uuid4()),
        )
        db.add_all([matching, other])
        db.commit()

        response = client.get("/emails", params={"batch_id": batch_id})

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(matching.id) in ids
        assert str(other.id) not in ids

    def test_list_emails_filters_by_status(self, client, db, faker):
        from app.models.email import Email

        batch_id = str(uuid4())
        opened = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Broadcast",
            body="Body",
            status="opened",
            provider="postmark",
            batch_id=batch_id,
        )
        delivered = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Broadcast",
            body="Body",
            status="delivered",
            provider="postmark",
            batch_id=batch_id,
        )
        db.add_all([opened, delivered])
        db.commit()

        response = client.get(
            "/emails", params={"batch_id": batch_id, "status": "opened"}
        )

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(opened.id) in ids
        assert str(delivered.id) not in ids

    def test_list_emails_filters_by_tag(self, client, db, faker):
        from app.models.email import Email

        tagged = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Tagged",
            body="Body",
            status="queued",
            provider="postmark",
            tags=["campaign-x", "vip"],
        )
        untagged = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Untagged",
            body="Body",
            status="queued",
            provider="postmark",
            tags=["other-tag"],
        )
        db.add_all([tagged, untagged])
        db.commit()

        response = client.get("/emails", params={"tag": "campaign-x"})

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(tagged.id) in ids
        assert str(untagged.id) not in ids

    def test_list_emails_filters_by_to_email(self, client, db, faker):
        from app.models.email import Email

        matching = Email(
            from_email=faker.email(),
            to_email="Alice.Smith@Example.com",
            subject="Broadcast",
            body="Body",
            status="queued",
            provider="postmark",
        )
        other = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Other",
            body="Body",
            status="queued",
            provider="postmark",
        )
        db.add_all([matching, other])
        db.commit()

        response = client.get("/emails", params={"to_email": "alice.smith"})

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(matching.id) in ids
        assert str(other.id) not in ids

    def test_list_emails_filters_by_subject(self, client, db, faker):
        from app.models.email import Email

        matching = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Welcome to Sendly",
            body="Body",
            status="queued",
            provider="postmark",
        )
        other = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Password reset",
            body="Body",
            status="queued",
            provider="postmark",
        )
        db.add_all([matching, other])
        db.commit()

        response = client.get("/emails", params={"subject": "welcome"})

        assert response.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in response.json()["items"]]
        assert str(matching.id) in ids
        assert str(other.id) not in ids

    def test_email_response_includes_tags_and_metadata(self, client, db, faker):
        from app.models.email import Email

        email = Email(
            from_email=faker.email(),
            to_email=faker.email(),
            subject="Subject",
            body="Body",
            status="queued",
            provider="postmark",
            batch_id="batch-123",
            tags=["a", "b"],
            metadata_={"campaign": "spring"},
        )
        db.add(email)
        db.commit()
        db.refresh(email)

        response = client.get(f"/emails/{email.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["batch_id"] == "batch-123"
        assert data["tags"] == ["a", "b"]
        assert data["metadata"] == {"campaign": "spring"}
