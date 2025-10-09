"""
Tests for the timezone bug fix in date_filter.py

This test documents the specific issue where the cron library incorrectly handled
timezone-aware timestamps, causing digest execution times to be calculated
incorrectly (e.g., 6 PM instead of 10 PM for NYC timezone).
"""

from datetime import datetime, timedelta
import pytz
from crontab import CronTab

from app.utils.date_filter import calculate_digest_date_range


class TestDateFilterTimezoneFix:
    """Test the timezone fix for cron execution time calculation."""

    def test_digest_date_range_with_america_new_york_timezone(self):
        """
        Test that digest date range calculation works correctly with America/New_York timezone.

        This specifically tests the bug where cron execution times were calculated
        4 hours earlier than expected due to timezone handling issues.

        The bug was: For a cron "0 22 * * *" (10 PM daily) in America/New_York timezone,
        the system was calculating execution times as 6 PM instead of 10 PM.
        """
        cron_expression = "0 22 * * *"  # 10 PM daily
        timezone_str = "America/New_York"

        # Test execution time: Sep 25, 2025 at 10 PM NYC (during EDT)
        tz = pytz.timezone(timezone_str)
        execution_time = tz.localize(datetime(2025, 9, 25, 22, 0, 0))

        # Calculate the date range
        start_date, end_date = calculate_digest_date_range(
            cron_expression, timezone_str, execution_time
        )

        # Convert back to NYC timezone for verification
        start_date_nyc = start_date.astimezone(tz)
        end_date_nyc = end_date.astimezone(tz)

        # For daily execution, the range should be from midnight of the previous day
        # to the execution time (10 PM)
        expected_start = tz.localize(datetime(2025, 9, 24, 0, 0, 0))  # Sep 24, midnight
        expected_end = execution_time  # Sep 25, 10 PM

        assert (
            start_date_nyc == expected_start
        ), f"Start date should be Sep 24 midnight NYC, got {start_date_nyc}"
        assert (
            end_date_nyc == expected_end
        ), f"End date should be Sep 25 10 PM NYC, got {end_date_nyc}"

        # Verify the bug fix: entry update at 2:14 PM on Sep 25 should be included
        entry_update_time = pytz.UTC.localize(datetime(2025, 9, 25, 14, 14, 3))
        is_included = start_date <= entry_update_time <= end_date

        assert is_included, (
            f"Entry update at {entry_update_time} should be included in range "
            f"{start_date} to {end_date}"
        )

    def test_digest_date_range_covers_entry_update_in_backfill_scenario(self):
        """
        Test the specific scenario from the bug report:
        - Entry update: Sep 25, 2025, 2:14:03 PM UTC
        - Digest config: 10 PM daily in America/New_York timezone
        - Backfill: last 5 days from Sep 26, 2025, 3 PM UTC
        """
        cron_expression = "0 22 * * *"  # 10 PM daily
        timezone_str = "America/New_York"

        # Entry update time from the bug report
        entry_update_time = pytz.UTC.localize(datetime(2025, 9, 25, 14, 14, 3))

        # Test the Sep 25 execution time (should include the entry)
        tz = pytz.timezone(timezone_str)
        sep25_execution = tz.localize(
            datetime(2025, 9, 25, 22, 0, 0)
        )  # Sep 25, 10 PM NYC

        start_date, end_date = calculate_digest_date_range(
            cron_expression, timezone_str, sep25_execution
        )

        # The entry should be included in the Sep 25 digest
        is_included = start_date <= entry_update_time <= end_date
        assert is_included, (
            f"Entry update {entry_update_time} should be included in Sep 25 digest range "
            f"{start_date} to {end_date}"
        )

        # Test the Sep 24 execution time (should NOT include the entry)
        sep24_execution = tz.localize(
            datetime(2025, 9, 24, 22, 0, 0)
        )  # Sep 24, 10 PM NYC

        start_date_24, end_date_24 = calculate_digest_date_range(
            cron_expression, timezone_str, sep24_execution
        )

        # The entry should NOT be included in the Sep 24 digest
        is_included_24 = start_date_24 <= entry_update_time <= end_date_24
        assert not is_included_24, (
            f"Entry update {entry_update_time} should NOT be included in Sep 24 digest range "
            f"{start_date_24} to {end_date_24}"
        )

    def test_cron_timezone_bug_reproduction(self):
        """
        Test that reproduces the original timezone bug and verifies it's fixed.

        The bug was in how the cron library handled timezone-aware timestamps
        when using default_utc=True.
        """
        cron_expression = "0 22 * * *"  # 10 PM daily
        tz = pytz.timezone("America/New_York")

        # Test time: Sep 26, 2025 at 11 AM NYC
        current_nyc = tz.localize(datetime(2025, 9, 26, 11, 0, 0))

        cron = CronTab(cron_expression)

        # This is how the code now works (fixed):
        # Convert to naive datetime to work around cron library bug
        current_nyc_naive = current_nyc.replace(tzinfo=None)
        prev_seconds_fixed = cron.previous(
            now=current_nyc_naive.timestamp(), default_utc=False
        )
        prev_execution_fixed = current_nyc - timedelta(seconds=abs(prev_seconds_fixed))

        # Expected: Sep 25, 10 PM NYC
        expected_execution = tz.localize(datetime(2025, 9, 25, 22, 0, 0))

        # Verify the fix works
        assert (
            prev_execution_fixed == expected_execution
        ), f"Fixed method should return {expected_execution}, got {prev_execution_fixed}"

        # For comparison, show what the buggy method would have returned:
        # (This demonstrates the bug but we don't want it to fail the test)
        prev_seconds_buggy = cron.previous(
            now=current_nyc.timestamp(), default_utc=True
        )
        prev_execution_buggy = current_nyc - timedelta(seconds=abs(prev_seconds_buggy))

        # The buggy method would return 6 PM instead of 10 PM (4 hour difference)
        time_difference = abs(
            (prev_execution_fixed - prev_execution_buggy).total_seconds()
        )

        # The difference should be exactly 4 hours (14400 seconds) due to the EDT offset
        assert time_difference == 14400, (
            f"Time difference between fixed and buggy methods should be 4 hours (14400 seconds), "
            f"got {time_difference} seconds"
        )

    def test_multiple_timezones_work_correctly(self):
        """Test that the fix works across different timezones."""
        cron_expression = "0 22 * * *"  # 10 PM daily

        test_timezones = [
            "America/New_York",  # EDT/EST
            "America/Los_Angeles",  # PDT/PST
            "Europe/London",  # BST/GMT
            "Asia/Tokyo",  # JST
        ]

        # Test time: a random date/time
        test_date = datetime(2025, 7, 15, 11, 30, 0)  # Summer time for most zones

        for timezone_str in test_timezones:
            tz = pytz.timezone(timezone_str)

            # Create an execution time for this timezone
            execution_time = tz.localize(datetime(2025, 7, 15, 22, 0, 0))  # 10 PM local

            # Calculate date range
            start_date, end_date = calculate_digest_date_range(
                cron_expression, timezone_str, execution_time
            )

            # Verify the end time matches the execution time when converted to UTC
            expected_end_utc = execution_time.astimezone(pytz.UTC)
            assert end_date == expected_end_utc, (
                f"For timezone {timezone_str}, end date {end_date} should equal "
                f"execution time in UTC {expected_end_utc}"
            )

            # Verify the start time is 24 hours before the end time (for daily cron)
            expected_start_utc = (
                (execution_time - timedelta(days=1))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(pytz.UTC)
            )

            assert start_date == expected_start_utc, (
                f"For timezone {timezone_str}, start date {start_date} should be "
                f"midnight of previous day in UTC {expected_start_utc}"
            )
