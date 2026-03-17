"""Email-related constants."""


class EmailStatus:
    """Email status constants."""

    QUEUED = "queued"
    SENT = "sent"          # accepted by provider
    DELIVERED = "delivered"  # confirmed in recipient mailbox
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"       # terminal
    COMPLAINED = "complained"  # terminal
    DROPPED = "dropped"       # terminal
    DEFERRED = "deferred"
    UNSUBSCRIBED = "unsubscribed"
    FAILED = "failed"         # terminal
