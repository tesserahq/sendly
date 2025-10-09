"""
Utility functions for calculating date ranges based on cron expressions and timezones.
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional
import pytz  # type: ignore
from crontab import CronTab  # type: ignore


def calculate_digest_date_range(
    cron_expression: str, timezone_str: str, execution_time: Optional[datetime] = None
) -> Tuple[datetime, datetime]:
    """
    Calculate the date range for digest entries based on cron expression and timezone.

    The logic:
    - For daily runs (e.g., "0 22 * * *"): 1 day range from start of previous day to execution time
    - For weekly runs (e.g., "0 22 * * 2"): 7 days range from previous occurrence to current execution
    - For other patterns: Calculate based on the frequency between executions

    Args:
        cron_expression: Cron expression (e.g., "0 22 * * *" for daily at 10pm)
        timezone_str: Timezone string (e.g., "America/New_York")
        execution_time: The time when the digest is being generated (defaults to now)

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    # Ensure we have a datetime object
    current_time: datetime = (
        execution_time if execution_time is not None else datetime.now()
    )

    # Parse the timezone
    try:
        tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        # Fallback to UTC if timezone is invalid
        tz = pytz.UTC

    # Convert execution time to the specified timezone
    if current_time.tzinfo is None:
        current_time = pytz.UTC.localize(current_time)
    execution_time_tz = current_time.astimezone(tz)

    # Parse the cron expression
    try:
        cron = CronTab(cron_expression)
    except Exception:
        # If cron parsing fails, default to daily range
        start_time = execution_time_tz.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        end_time = execution_time_tz
        return start_time.astimezone(pytz.UTC), end_time.astimezone(pytz.UTC)

    # Calculate the previous execution time
    # CronTab.next() gives seconds until next execution, we want the previous one
    # So we go back in time to find when it would have last run
    previous_execution = _find_previous_cron_execution(cron, execution_time_tz)

    # Determine the frequency of execution to calculate appropriate date range
    frequency_days = _determine_cron_frequency_days(cron_expression)

    if frequency_days == 1:
        # Daily execution: range from start of the day of previous execution to current execution
        start_time = previous_execution.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif frequency_days == 7:
        # Weekly execution: range from previous execution to current execution
        start_time = previous_execution
    else:
        # Other frequencies: use the calculated frequency
        start_time = execution_time_tz - timedelta(days=frequency_days)

    end_time = execution_time_tz

    # Convert to UTC for database queries
    return start_time.astimezone(pytz.UTC), end_time.astimezone(pytz.UTC)


def _find_previous_cron_execution(cron: CronTab, current_time: datetime) -> datetime:
    """
    Find the previous time this cron would have executed before current_time.

    Args:
        cron: Parsed CronTab object
        current_time: Current time in the target timezone

    Returns:
        Previous execution datetime in the same timezone as current_time
    """
    # Start from current time and go backwards to find when it would have last run
    check_time = current_time

    # Go back up to 8 days to find the previous execution (covers weekly + buffer)
    for _ in range(8 * 24 * 60):  # Check every minute for up to 8 days
        check_time = check_time - timedelta(minutes=1)

        # Create a cron object at this check time to see if it would execute
        # We need to check if this minute matches the cron pattern
        if _matches_cron_pattern(cron, check_time):
            return check_time

    # If we can't find a previous execution, default to 24 hours ago
    return current_time - timedelta(days=1)


def _matches_cron_pattern(cron: CronTab, check_time: datetime) -> bool:
    """
    Check if a given datetime matches the cron pattern.

    Args:
        cron: Parsed CronTab object
        check_time: Time to check against the cron pattern

    Returns:
        True if the time matches the cron pattern
    """
    try:
        # Get the next execution time from just before our check time
        test_time = check_time - timedelta(minutes=1)

        # Convert to naive datetime in the local timezone to work around cron library bug
        # The cron library has issues with timezone-aware timestamps
        if test_time.tzinfo is not None:
            # Convert to naive datetime (this assumes the cron expression is in the same timezone)
            test_time_naive = test_time.replace(tzinfo=None)
        else:
            test_time_naive = test_time

        # Calculate how many seconds until the next execution from test_time
        next_seconds = cron.next(now=test_time_naive.timestamp())

        # If the next execution is within the next minute, it matches our check_time
        return next_seconds <= 60
    except Exception:
        return False


def _determine_cron_frequency_days(cron_expression: str) -> int:
    """
    Determine the frequency in days based on the cron expression pattern.

    Args:
        cron_expression: Cron expression string

    Returns:
        Number of days between executions (1 for daily, 7 for weekly, etc.)
    """
    parts = cron_expression.strip().split()

    # Handle different cron formats (5, 6, or 7 parts)
    if len(parts) == 5:
        # Standard format: minute hour day_of_month month day_of_week
        minute, hour, day_of_month, month, day_of_week = parts
    elif len(parts) == 6:
        # With seconds: second minute hour day_of_month month day_of_week
        second, minute, hour, day_of_month, month, day_of_week = parts
    elif len(parts) == 7:
        # With year: second minute hour day_of_month month day_of_week year
        second, minute, hour, day_of_month, month, day_of_week, year = parts
    else:
        # Default to daily if format is unexpected
        return 1

    # Check if it's a weekly pattern (specific day of week)
    if day_of_week != "*" and day_of_week != "?":
        # If day of week is specified and not wildcard, it's likely weekly
        return 7

    # Check if it's a daily pattern (day_of_month is * or ?)
    if day_of_month == "*" or day_of_month == "?":
        return 1

    # Check for monthly patterns
    if day_of_month.isdigit():
        return 30  # Approximate monthly

    # Check for other patterns with step values
    if "/" in day_of_month:
        try:
            step = int(day_of_month.split("/")[-1])
            return step
        except ValueError:
            pass

    if "/" in day_of_week:
        try:
            step = int(day_of_week.split("/")[-1])
            return step * 7  # Weekly step
        except ValueError:
            pass

    # Default to daily
    return 1
