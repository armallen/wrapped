#!/usr/bin/env python3
"""
Jira Activity Summary Script
Fetches Jira statistics using the REST API directly (no MCP required)

Usage:
    python jira-activity-summary.py [start-date] [end-date]
    python jira-activity-summary.py 2025-02-28 2026-02-02

Setup:
    1. Generate an API token: https://id.atlassian.com/manage-profile/security/api-tokens
    2. Set environment variables:
       export ATLASSIAN_USER="your-email@example.com"
       export ATLASSIAN_TOKEN="your-api-token"
       export ATLASSIAN_SITE="your-site.atlassian.net"
"""

import argparse
import logging
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration for Jira API access and date ranges."""

    atlassian_user: str
    atlassian_token: str
    atlassian_site: str
    start_date: str
    end_date: str
    pto_days: int = 0

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """Create config from parsed arguments."""
        return cls(
            atlassian_user=args.user,
            atlassian_token=args.token,
            atlassian_site=args.site,
            start_date=args.start_date,
            end_date=args.end_date,
            pto_days=args.ptos,
        )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate Jira activity summary report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "start_date",
        nargs="?",
        default="2025-02-28",
        help="Start date in YYYY-MM-DD format (default: 2025-02-28)",
    )
    parser.add_argument(
        "end_date",
        nargs="?",
        default="2026-02-02",
        help="End date in YYYY-MM-DD format (default: 2026-02-02)",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("ATLASSIAN_USER"),
        help="Atlassian user email (default: $ATLASSIAN_USER)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("ATLASSIAN_TOKEN"),
        help="Atlassian API token (default: $ATLASSIAN_TOKEN)",
    )
    parser.add_argument(
        "--site",
        default=os.environ.get("ATLASSIAN_SITE", "swift-nav.atlassian.net"),
        help="Atlassian site URL (default: $ATLASSIAN_SITE or swift-nav.atlassian.net)",
    )
    parser.add_argument(
        "--ptos",
        type=int,
        default=0,
        help="Number of PTO days to exclude from calculations (default: 0)",
    )

    return parser.parse_args()


def check_auth(config: Config) -> None:
    """Check if authentication is configured."""
    if not config.atlassian_user or not config.atlassian_token:
        logger.error("Error: Atlassian authentication not configured")
        logger.info("")
        logger.info("Please set the following environment variables:")
        logger.info('  export ATLASSIAN_USER="your-email@example.com"')
        logger.info('  export ATLASSIAN_TOKEN="your-api-token"')
        logger.info('  export ATLASSIAN_SITE="your-site.atlassian.net"  # optional')
        logger.info("")
        logger.info("Or pass them as command line arguments:")
        logger.info('  --user "your-email@example.com"')
        logger.info('  --token "your-api-token"')
        logger.info('  --site "your-site.atlassian.net"')
        logger.info("")
        logger.info("Generate an API token here:")
        logger.info("  https://id.atlassian.com/manage-profile/security/api-tokens")
        logger.info("")
        sys.exit(1)


def jira_search(
    config: Config, jql: str, fields: list[str] | None = None, max_results: int = 100
) -> list[dict]:
    """
    Search Jira using JQL with pagination.

    Args:
        config: Configuration object
        jql: JQL query string
        fields: List of fields to retrieve (default: summary, status, issuetype)
        max_results: Results per page (max 100)

    Returns:
        List of all issues matching the query
    """
    if fields is None:
        fields = ["summary", "status", "issuetype", "created", "resolved"]

    # Use the NEW search/jql endpoint with nextPageToken pagination
    url = f"https://{config.atlassian_site}/rest/api/3/search/jql"
    auth = (config.atlassian_user, config.atlassian_token)

    all_issues = []
    next_page_token = None
    max_iterations = 100  # Safety limit to prevent infinite loops

    iteration = 0
    while iteration < max_iterations:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ",".join(fields),
        }

        # Add nextPageToken if we have one (not for first request)
        if next_page_token:
            params["nextPageToken"] = next_page_token

        response = requests.get(url, auth=auth, params=params, timeout=30)

        if response.status_code != 200:
            logger.error("Error: Failed to fetch data from Jira")
            logger.error(f"Status code: {response.status_code}")
            logger.error(f"Response: {response.text}")
            sys.exit(1)

        data = response.json()

        issues = data.get("issues", [])
        all_issues.extend(issues)

        # Get nextPageToken from response for pagination
        next_page_token = data.get("nextPageToken")
        total = data.get("total", len(all_issues))

        # Show progress
        if total > 0:
            logger.info(f"  Fetched {len(all_issues)}/{total} issues...")
        else:
            logger.info(f"  Fetched {len(all_issues)} issues...")

        # Check if we got all results
        if len(issues) == 0:
            logger.debug("  No more issues returned, stopping pagination")
            break

        # If there's no nextPageToken, we're done
        if not next_page_token:
            logger.debug("  No nextPageToken, last page reached")
            break

        iteration += 1

    if iteration >= max_iterations:
        logger.warning(
            f"  Hit maximum iteration limit ({max_iterations}), stopping. This might indicate an API issue."
        )

    logger.info(f"  Fetched {len(all_issues)} issues... Done!")
    return all_issues


def count_by_type(issues: list[dict]) -> Counter:
    """Count issues by type."""
    types = [issue["fields"]["issuetype"]["name"] for issue in issues]
    return Counter(types)


def sum_story_points(
    issues: list[dict], field_name: str = "customfield_10014"
) -> tuple[float, int]:
    """Sum story points from issues."""
    total = 0.0
    count = 0

    for issue in issues:
        sp = issue["fields"].get(field_name)
        if sp is not None:
            try:
                total += float(sp)
                count += 1
            except (ValueError, TypeError):
                pass

    return total, count


def calculate_working_weeks(
    start_date: str, end_date: str, pto_days: int
) -> tuple[int, float, int, float]:
    """Calculate working weeks in the period (5-day work weeks, excluding weekends)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # Calculate total calendar days
    total_days = (end - start).days
    total_weeks = total_days / 7  # Calendar weeks

    # Count weekdays (Mon-Fri) in the period
    weekdays = 0
    current = start
    while current < end:
        if current.weekday() < 5:  # Monday=0, Friday=4
            weekdays += 1
        current += timedelta(days=1)

    # Calculate working days (weekdays - PTO)
    working_days = weekdays - pto_days
    working_weeks = working_days / 5  # 5-day working weeks

    return total_days, total_weeks, working_days, working_weeks


def print_header(config: Config) -> None:
    """Print report header."""
    logger.info("╔════════════════════════════════════════════════════════════════╗")
    logger.info("║        Jira Activity Summary")
    logger.info(f"║        Period: {config.start_date} to {config.end_date}")
    logger.info("╚════════════════════════════════════════════════════════════════╝")
    logger.info("")


def print_tickets_created(config: Config, created_issues: list[dict]) -> None:
    """Print tickets created section."""
    logger.info("📝 Tickets You Created")
    logger.info("════════════════════════════════════════════════════════════════")
    logger.info(f"  Total Tickets Created: {len(created_issues)}")

    created_types = count_by_type(created_issues)
    logger.info("\n  Breakdown by Type:")
    for issue_type, count in created_types.most_common():
        percentage = (count / len(created_issues) * 100) if created_issues else 0
        logger.info(f"    • {issue_type}: {count} ({percentage:.1f}%)")

    logger.info("")


def print_tickets_resolved(config: Config, resolved_issues: list[dict]) -> None:
    """Print tickets resolved section."""
    logger.info("✅ Tickets You Resolved/Closed")
    logger.info("════════════════════════════════════════════════════════════════")
    logger.info(f"  Total Tickets Resolved: {len(resolved_issues)}")

    resolved_types = count_by_type(resolved_issues)
    logger.info("\n  Breakdown by Type:")
    for issue_type, count in resolved_types.most_common():
        percentage = (count / len(resolved_issues) * 100) if resolved_issues else 0
        logger.info(f"    • {issue_type}: {count} ({percentage:.1f}%)")

    logger.info("")


def print_bugs_resolved(config: Config, bug_issues: list[dict]) -> None:
    """Print bugs resolved section."""
    logger.info("🐛 Bugs You Resolved")
    logger.info("════════════════════════════════════════════════════════════════")
    logger.info(f"  Total Bugs Resolved: {len(bug_issues)}")
    logger.info("")


def print_story_points(
    config: Config, resolved_issues: list[dict]
) -> tuple[float, int]:
    """Print story points section and return totals."""
    logger.info("⭐ Story Points Completed")
    logger.info("════════════════════════════════════════════════════════════════")

    total_sp, count_with_sp = sum_story_points(resolved_issues)

    logger.info(f"  Total Story Points: {total_sp:.2f}")
    logger.info(f"  Tickets with story points: {count_with_sp}/{len(resolved_issues)}")

    if count_with_sp < len(resolved_issues):
        logger.warning("  Note: Not all tickets have story points assigned")

    logger.info("")
    return total_sp, count_with_sp


def print_overall_statistics(
    config: Config,
    created_issues: list[dict],
    resolved_issues: list[dict],
    bug_issues: list[dict],
    total_sp: float,
    working_weeks: float,
) -> None:
    """Print overall statistics section."""
    logger.info("📊 Overall Statistics")
    logger.info("════════════════════════════════════════════════════════════════")

    if working_weeks > 0:
        created_per_week = len(created_issues) / working_weeks
        resolved_per_week = len(resolved_issues) / working_weeks
        bugs_per_week = len(bug_issues) / working_weeks
        sp_per_week = total_sp / working_weeks

        logger.info(f"  Tickets Created per Week: {created_per_week:.2f}")
        logger.info(f"  Tickets Resolved per Week: {resolved_per_week:.2f}")
        logger.info(f"  Bugs Resolved per Week: {bugs_per_week:.2f}")
        logger.info(f"  Story Points per Week: {sp_per_week:.2f}")

    logger.info("")


def print_summary(config: Config) -> None:
    """Print closing summary."""
    logger.info("╔════════════════════════════════════════════════════════════════╗")
    logger.info("║  Summary complete!")
    logger.info("╚════════════════════════════════════════════════════════════════╝")
    logger.info("")
    logger.info("💡 Tip: Save this output to a file:")
    logger.info(
        f"   python jira-activity-summary.py {config.start_date} {config.end_date} > jira_summary.txt"
    )
    logger.info("")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    config = Config.from_args(args)

    print_header(config)
    check_auth(config)

    logger.info("Connecting to Jira...")
    logger.info(f"Site: {config.atlassian_site}")
    logger.info(f"User: {config.atlassian_user}")
    logger.info("")

    # Calculate time periods
    total_days, total_weeks, working_days, working_weeks = calculate_working_weeks(
        config.start_date, config.end_date, config.pto_days
    )

    logger.info(f"Period: {total_days} days ({total_weeks:.1f} calendar weeks)")
    logger.info(f"Weekdays in period: {working_days + config.pto_days} days")
    if config.pto_days > 0:
        logger.info(
            f"Working days (excluding {config.pto_days} PTO days): {working_days} days ({working_weeks:.1f} weeks)"
        )
    else:
        logger.info(f"Working days: {working_days} days ({working_weeks:.1f} weeks)")
    logger.info("")

    # Fetch tickets created
    jql_created = f"reporter = currentUser() AND created >= '{config.start_date}' AND created <= '{config.end_date}'"
    created_issues = jira_search(config, jql_created)
    print_tickets_created(config, created_issues)

    # Fetch tickets resolved
    jql_resolved = f"assignee = currentUser() AND resolved >= '{config.start_date}' AND resolved <= '{config.end_date}'"
    resolved_issues = jira_search(
        config,
        jql_resolved,
        fields=["summary", "status", "issuetype", "resolved", "customfield_10014"],
    )
    print_tickets_resolved(config, resolved_issues)

    # Fetch bugs resolved
    jql_bugs = f"assignee = currentUser() AND type = Bug AND resolved >= '{config.start_date}' AND resolved <= '{config.end_date}'"
    bug_issues = jira_search(config, jql_bugs)
    print_bugs_resolved(config, bug_issues)

    # Story points
    total_sp, count_with_sp = print_story_points(config, resolved_issues)

    # Overall statistics
    print_overall_statistics(
        config, created_issues, resolved_issues, bug_issues, total_sp, working_weeks
    )

    # Summary
    print_summary(config)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
