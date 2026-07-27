"""Unit tests for EmailRenderingService: template resolution, layout wrapping,
variable interpolation, and error cases. No DB, no provider — TemplateRepository
is patched at the module level EmailRenderingService imports it from.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.providers.base import EmailCreateRequest
from app.services.email_rendering_service import (
    ConflictingContentError,
    EmailRenderingService,
    MissingFieldError,
    TemplateNotFoundError,
    TemplateSyntaxError,
)


def _make_template(**overrides):
    defaults = dict(
        id="template-id",
        html="<p>Hello ${name}</p>",
        subject="Hi ${name}",
        from_email="template@example.com",
        layout=None,
        layout_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_req(**overrides):
    defaults = dict(to=["user@example.com"])
    defaults.update(overrides)
    return EmailCreateRequest(**defaults)


class TestResolveInline:
    def test_renders_inline_html_with_variables(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>Hi ${name}</p>",
            subject="Subject",
            from_email="from@example.com",
            template_variables={"name": "Alice"},
        )
        result = service.resolve_inline(req)
        assert "Hi Alice" in result.html
        assert result.subject == "Subject"
        assert result.from_email == "from@example.com"

    def test_missing_from_email_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(html="<p>hi</p>", subject="Subject")
        with pytest.raises(MissingFieldError):
            service.resolve_inline(req)

    def test_missing_subject_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(html="<p>hi</p>", from_email="from@example.com")
        with pytest.raises(MissingFieldError):
            service.resolve_inline(req)

    def test_missing_html_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(subject="Subject", from_email="from@example.com")
        with pytest.raises(MissingFieldError):
            service.resolve_inline(req)


class TestResolveTemplate:
    def test_renders_template_without_layout(self):
        template = _make_template()
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(
                template_id="00000000-0000-0000-0000-000000000000",
                template_variables={"name": "Bob"},
            )
            result = service.resolve_template(req)

        assert "Hello Bob" in result.html
        assert result.subject == "Hi Bob"
        assert result.from_email == "template@example.com"

    def test_wraps_template_in_layout(self):
        layout = SimpleNamespace(html="<html>${content}</html>")
        template = _make_template(layout=layout, layout_id="layout-id")
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template_by_alias.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(
                template_alias="welcome", template_variables={"name": "Carol"}
            )
            result = service.resolve_template(req)

        assert result.html.startswith("<html>")
        assert "Hello Carol" in result.html

    def test_soft_deleted_layout_falls_back_silently(self):
        # layout_id set but layout relationship is None (soft-deleted layout)
        template = _make_template(layout=None, layout_id="missing-layout-id")
        with (
            patch(
                "app.services.email_rendering_service.TemplateRepository"
            ) as MockRepo,
            patch("app.services.email_rendering_service.logger") as mock_logger,
        ):
            MockRepo.return_value.get_template.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(
                template_id="00000000-0000-0000-0000-000000000000",
                template_variables={"name": "Dana"},
            )
            result = service.resolve_template(req)

        assert "Hello Dana" in result.html
        mock_logger.warning.assert_called_once()

    def test_template_not_found_raises(self):
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template_by_alias.return_value = None
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(template_alias="nonexistent")
            with pytest.raises(TemplateNotFoundError):
                service.resolve_template(req)

    def test_missing_from_email_raises(self):
        template = _make_template(from_email=None)
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(template_id="00000000-0000-0000-0000-000000000000")
            with pytest.raises(MissingFieldError):
                service.resolve_template(req)


class TestRender:
    def test_missing_variable_raises_missing_field_error(self):
        with pytest.raises(MissingFieldError):
            EmailRenderingService.render("Hello ${name}")

    def test_syntax_error_raises_template_syntax_error(self):
        with pytest.raises(TemplateSyntaxError):
            EmailRenderingService.render("<% this is not valid mako %>")

    def test_nested_dict_dot_access(self):
        result = EmailRenderingService.render(
            "${common.product_name}", common={"product_name": "Acme"}
        )
        assert result == "Acme"

    def test_year_is_available_by_default(self):
        result = EmailRenderingService.render("${year}")
        assert result.isdigit()


class TestValidate:
    """validate() checks content-level requirements without rendering — no
    recipient-specific data needed, so it's safe to run once up front."""

    def test_inline_html_missing_subject_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(html="<p>hi</p>", from_email="from@example.com")
        with pytest.raises(MissingFieldError):
            service.validate(req)

    def test_inline_html_missing_from_email_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(html="<p>hi</p>", subject="Subject")
        with pytest.raises(MissingFieldError):
            service.validate(req)

    def test_neither_template_nor_inline_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req()
        with pytest.raises(MissingFieldError):
            service.validate(req)

    def test_both_template_and_inline_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(html="<p>hi</p>", template_alias="welcome")
        with pytest.raises(ConflictingContentError):
            service.validate(req)

    def test_unresolvable_template_raises(self):
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template_by_alias.return_value = None
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(template_alias="nonexistent")
            with pytest.raises(TemplateNotFoundError):
                service.validate(req)

    def test_valid_inline_html_passes(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>", subject="Subject", from_email="from@example.com"
        )
        service.validate(req)  # does not raise

    def test_valid_template_passes(self):
        template = _make_template()
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(template_id="00000000-0000-0000-0000-000000000000")
            service.validate(req)  # does not raise
