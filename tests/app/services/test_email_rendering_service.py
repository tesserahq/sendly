"""Unit tests for EmailRenderingService: template resolution, layout wrapping,
variable interpolation, and error cases. No DB, no provider — TemplateRepository
is patched at the module level EmailRenderingService imports it from.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.providers.base import EmailCreateRequest
from app.schemas.broadcast import ContentSpec
from app.services.email_rendering_service import (
    ConflictingContentError,
    EmailRenderingService,
    LayoutNotFoundError,
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
        reply_to=None,
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

    def test_reply_to_passed_through(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>",
            subject="Subject",
            from_email="from@example.com",
            reply_to="reply@example.com",
        )
        result = service.resolve_inline(req)
        assert result.reply_to == "reply@example.com"

    def test_reply_to_defaults_to_none(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>", subject="Subject", from_email="from@example.com"
        )
        result = service.resolve_inline(req)
        assert result.reply_to is None

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
        assert result.reply_to is None

    def test_reply_to_falls_back_to_template(self):
        template = _make_template(reply_to="template-reply@example.com")
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

        assert result.reply_to == "template-reply@example.com"

    def test_reply_to_in_payload_overrides_template(self):
        template = _make_template(reply_to="template-reply@example.com")
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(
                template_id="00000000-0000-0000-0000-000000000000",
                template_variables={"name": "Bob"},
                reply_to="payload-reply@example.com",
            )
            result = service.resolve_template(req)

        assert result.reply_to == "payload-reply@example.com"

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

    def test_missing_variable_is_named_in_error_message(self):
        with pytest.raises(MissingFieldError) as exc_info:
            EmailRenderingService.render(
                "Hello ${first_name} ${last_name}", first_name="Ada"
            )
        assert "last_name" in str(exc_info.value)
        assert "first_name" not in str(exc_info.value).split("Variables provided")[0]

    def test_missing_attribute_on_provided_namespace_not_reported_as_missing(self):
        with pytest.raises(MissingFieldError) as exc_info:
            EmailRenderingService.render(
                "${company.name}", company={"other_field": "x"}
            )
        # `company` was provided, so it shouldn't be listed as a missing
        # variable — the underlying AttributeError already names the
        # missing attribute.
        assert "Missing variable(s)" not in str(exc_info.value)

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


class TestInlineLayout:
    """Inline html wrapped in an already-resolved layout (the broadcast
    snapshot), plus Mako-rendered inline subjects — parity with templates."""

    def test_renders_inline_subject_with_variables(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>",
            subject="Hi ${name}",
            from_email="from@example.com",
            template_variables={"name": "Alice"},
        )
        assert service.resolve_inline(req).subject == "Hi Alice"

    def test_wraps_inline_html_in_layout(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>Hi ${name}</p>",
            subject="Subject",
            from_email="from@example.com",
            template_variables={"name": "Alice"},
        )
        result = service.resolve(
            req,
            layout_html="<div class='wrap'>${content}<footer>${name}</footer></div>",
        )
        assert result.html == (
            "<div class='wrap'><p>Hi Alice</p><footer>Alice</footer></div>"
        )

    def test_inline_without_layout_is_unwrapped(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>", subject="Subject", from_email="from@example.com"
        )
        assert service.resolve(req).html == "<p>hi</p>"

    def test_layout_html_is_ignored_for_templates(self):
        template = _make_template()
        with patch(
            "app.services.email_rendering_service.TemplateRepository"
        ) as MockRepo:
            MockRepo.return_value.get_template_by_alias.return_value = template
            service = EmailRenderingService(db=MagicMock())
            req = _make_req(template_alias="welcome", template_variables={"name": "A"})
            result = service.resolve(req, layout_html="<div>${content}</div>")
        assert result.html == "<p>Hello A</p>"

    def test_missing_variable_in_subject_raises(self):
        service = EmailRenderingService(db=MagicMock())
        req = _make_req(
            html="<p>hi</p>", subject="Hi ${name}", from_email="from@example.com"
        )
        with pytest.raises(MissingFieldError, match="name"):
            service.resolve_inline(req)


class TestResolveLayoutHtml:
    def test_no_reference_returns_none(self):
        with patch("app.services.email_rendering_service.LayoutRepository") as MockRepo:
            service = EmailRenderingService(db=MagicMock())
            assert service.resolve_layout_html(None, None) is None
        MockRepo.assert_not_called()

    def test_resolves_by_id(self):
        with patch("app.services.email_rendering_service.LayoutRepository") as MockRepo:
            MockRepo.return_value.get_layout.return_value = SimpleNamespace(
                html="<div>${content}</div>"
            )
            service = EmailRenderingService(db=MagicMock())
            assert service.resolve_layout_html("id", None) == "<div>${content}</div>"

    def test_resolves_by_alias(self):
        with patch("app.services.email_rendering_service.LayoutRepository") as MockRepo:
            MockRepo.return_value.get_layout_by_alias.return_value = SimpleNamespace(
                html="<div>${content}</div>"
            )
            service = EmailRenderingService(db=MagicMock())
            assert service.resolve_layout_html(None, "brand") == "<div>${content}</div>"

    def test_id_wins_over_alias(self):
        with patch("app.services.email_rendering_service.LayoutRepository") as MockRepo:
            MockRepo.return_value.get_layout.return_value = SimpleNamespace(
                html="by-id"
            )
            service = EmailRenderingService(db=MagicMock())
            assert service.resolve_layout_html("id", "brand") == "by-id"
        MockRepo.return_value.get_layout_by_alias.assert_not_called()

    def test_missing_layout_raises(self):
        with patch("app.services.email_rendering_service.LayoutRepository") as MockRepo:
            MockRepo.return_value.get_layout.return_value = None
            service = EmailRenderingService(db=MagicMock())
            with pytest.raises(LayoutNotFoundError):
                service.resolve_layout_html("id", None)


class TestValidateLayout:
    def test_layout_with_template_raises(self):
        service = EmailRenderingService(db=MagicMock())
        spec = ContentSpec(template_alias="welcome", layout_alias="brand")
        with pytest.raises(ConflictingContentError):
            service.validate(spec)

    def test_layout_with_inline_html_passes(self):
        service = EmailRenderingService(db=MagicMock())
        spec = ContentSpec(
            html="<p>hi</p>",
            subject="Subject",
            from_email="from@example.com",
            layout_alias="brand",
        )
        service.validate(spec)  # does not raise
