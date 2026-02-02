#!/bin/bash

# GitHub Activity Summary Script
# Usage: ./github-activity-summary.sh [start-date] [end-date]
# Example: ./github-activity-summary.sh 2025-02-28 2026-02-02

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Default date range
START_DATE=${1:-"2025-02-28"}
END_DATE=${2:-"2026-02-02"}

echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║        GitHub Activity Summary - $(gh api user -q .login)${NC}"
echo -e "${BOLD}${CYAN}║        Period: ${START_DATE} to ${END_DATE}${NC}"
echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if gh and jq are installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: gh CLI is not installed${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is not installed (brew install jq)${NC}"
    exit 1
fi

echo -e "${YELLOW}Fetching your GitHub activity...${NC}"
echo ""

# Get username once
USERNAME=$(gh api user -q .login)

echo -e "${CYAN}Using search queries:${NC}"
echo -e "  Author: author:${USERNAME} is:pr created:${START_DATE}..${END_DATE}"
echo -e "  Reviewer: reviewed-by:${USERNAME} is:pr created:${START_DATE}..${END_DATE}"
echo ""

# ============================================================================
# AUTHORED PRS
# ============================================================================
echo -e "${BOLD}${BLUE}📝 Pull Requests You Created${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Use GraphQL for authored PRs to get complete data including mergedAt
SEARCH_QUERY="author:${USERNAME} is:pr created:${START_DATE}..${END_DATE}"
AUTHORED_PRS=$(gh api graphql --paginate -f query="
query(\$endCursor: String) {
  search(
    query: \"${SEARCH_QUERY}\"
    type: ISSUE
    first: 100
    after: \$endCursor
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on PullRequest {
        number
        title
        url
        state
        repository {
          nameWithOwner
        }
        createdAt
        closedAt
        mergedAt
        additions
        deletions
      }
    }
  }
}" --jq '.data.search.nodes' | jq -s 'add')

TOTAL_AUTHORED=$(echo "$AUTHORED_PRS" | jq 'length')

# Warn if we hit GitHub's 1000 result limit
if [ "$TOTAL_AUTHORED" -eq 1000 ]; then
    echo -e "${YELLOW}⚠️  Warning: Hit GitHub's 1000 result limit for authored PRs${NC}"
    echo -e "${YELLOW}   Results may be incomplete. Consider using a shorter date range.${NC}"
    echo ""
fi

MERGED_AUTHORED=$(echo "$AUTHORED_PRS" | jq '[.[] | select(.mergedAt != null)] | length')
OPEN_AUTHORED=$(echo "$AUTHORED_PRS" | jq '[.[] | select(.state == "OPEN")] | length')
CLOSED_AUTHORED=$(echo "$AUTHORED_PRS" | jq '[.[] | select(.state == "CLOSED" and .mergedAt == null)] | length')

TOTAL_ADDITIONS=$(echo "$AUTHORED_PRS" | jq '[.[] | .additions] | add // 0')
TOTAL_DELETIONS=$(echo "$AUTHORED_PRS" | jq '[.[] | .deletions] | add // 0')
NET_CHANGE=$((TOTAL_ADDITIONS - TOTAL_DELETIONS))

echo -e "  ${GREEN}Total PRs Created:${NC} ${BOLD}$TOTAL_AUTHORED${NC}"
echo -e "  ${GREEN}Merged:${NC} ${BOLD}$MERGED_AUTHORED${NC} | ${YELLOW}Open:${NC} ${BOLD}$OPEN_AUTHORED${NC} | ${RED}Closed:${NC} ${BOLD}$CLOSED_AUTHORED${NC}"

# Show date range of results
FIRST_PR_DATE=$(echo "$AUTHORED_PRS" | jq -r '[.[] | .createdAt] | sort | .[0] // "N/A" | .[0:10]')
LAST_PR_DATE=$(echo "$AUTHORED_PRS" | jq -r '[.[] | .createdAt] | sort | .[-1] // "N/A" | .[0:10]')
echo -e "  ${CYAN}Date range of results:${NC} ${FIRST_PR_DATE} to ${LAST_PR_DATE}"
echo -e "  ${GREEN}Lines Added:${NC} ${BOLD}+$TOTAL_ADDITIONS${NC}"
echo -e "  ${RED}Lines Deleted:${NC} ${BOLD}-$TOTAL_DELETIONS${NC}"
echo -e "  ${CYAN}Net Change:${NC} ${BOLD}$NET_CHANGE${NC} lines"
echo ""

# Repository breakdown
echo -e "${BOLD}  Top Repositories You Contributed To:${NC}"
echo "$AUTHORED_PRS" | jq -r '[.[] | .repository.nameWithOwner] | group_by(.) | map({repo: .[0], count: length}) | sort_by(.count) | reverse | .[:5] | .[] | "    • \(.repo): \(.count) PRs"'
echo ""

# ============================================================================
# REVIEWED PRS
# ============================================================================
echo -e "${BOLD}${BLUE}👀 Pull Requests You Reviewed${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Note: GitHub's search doesn't have a simple "reviewed-by" filter in gh search
# We need to use GraphQL API for more accurate review data
echo -e "${YELLOW}Fetching review data (this may take a moment)...${NC}"

# GraphQL query to get reviewed PRs
REVIEW_SEARCH_QUERY="reviewed-by:${USERNAME} is:pr created:${START_DATE}..${END_DATE}"
REVIEWED_PRS=$(gh api graphql --paginate -f query="
query(\$endCursor: String) {
  search(
    query: \"${REVIEW_SEARCH_QUERY}\"
    type: ISSUE
    first: 100
    after: \$endCursor
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on PullRequest {
        number
        title
        url
        repository {
          nameWithOwner
        }
        author {
          login
        }
        state
        createdAt
        reviews(author: \"${USERNAME}\") {
          totalCount
        }
      }
    }
  }
}" --jq '.data.search.nodes' | jq -s 'add')

TOTAL_REVIEWED=$(echo "$REVIEWED_PRS" | jq 'length')

# Warn if we hit GitHub's 1000 result limit
if [ "$TOTAL_REVIEWED" -eq 1000 ]; then
    echo -e "${YELLOW}⚠️  Warning: Hit GitHub's 1000 result limit for reviewed PRs${NC}"
    echo -e "${YELLOW}   Results may be incomplete. Consider using a shorter date range.${NC}"
    echo ""
fi

UNIQUE_AUTHORS=$(echo "$REVIEWED_PRS" | jq '[.[] | .author.login] | unique | length')
TOTAL_REVIEW_COMMENTS=$(echo "$REVIEWED_PRS" | jq '[.[] | .reviews.totalCount] | add // 0')

echo -e "  ${GREEN}Total PRs Reviewed:${NC} ${BOLD}$TOTAL_REVIEWED${NC}"
echo -e "  ${GREEN}Unique Authors Collaborated With:${NC} ${BOLD}$UNIQUE_AUTHORS${NC} people"
echo -e "  ${GREEN}Total Reviews/Comments:${NC} ${BOLD}$TOTAL_REVIEW_COMMENTS${NC}"
echo ""

# Top collaborators
echo -e "${BOLD}  Top Collaborators (authors you reviewed):${NC}"
echo "$REVIEWED_PRS" | jq -r '[.[] | .author.login] | group_by(.) | map({author: .[0], count: length}) | sort_by(.count) | reverse | .[:10] | .[] | "    • \(.author): \(.count) PRs reviewed"'
echo ""

# Top repositories reviewed
echo -e "${BOLD}  Top Repositories You Reviewed:${NC}"
echo "$REVIEWED_PRS" | jq -r '[.[] | .repository.nameWithOwner] | group_by(.) | map({repo: .[0], count: length}) | sort_by(.count) | reverse | .[:5] | .[] | "    • \(.repo): \(.count) PRs reviewed"'
echo ""

# ============================================================================
# OVERALL STATISTICS
# ============================================================================
echo -e "${BOLD}${BLUE}📊 Overall Statistics${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

TOTAL_PRS=$((TOTAL_AUTHORED + TOTAL_REVIEWED))
AVG_CHANGES_PER_PR=0
if [ "$TOTAL_AUTHORED" -gt 0 ]; then
    AVG_CHANGES_PER_PR=$(((TOTAL_ADDITIONS + TOTAL_DELETIONS) / TOTAL_AUTHORED))
fi

# Calculate time period in days
START_SECONDS=$(date -j -f "%Y-%m-%d" "$START_DATE" "+%s" 2>/dev/null || date -d "$START_DATE" "+%s")
END_SECONDS=$(date -j -f "%Y-%m-%d" "$END_DATE" "+%s" 2>/dev/null || date -d "$END_DATE" "+%s")
DAYS_DIFF=$(( (END_SECONDS - START_SECONDS) / 86400 ))

echo -e "  ${GREEN}Total PR Interactions:${NC} ${BOLD}$TOTAL_PRS${NC} (authored + reviewed)"
echo -e "  ${GREEN}Average Changes per PR:${NC} ${BOLD}$AVG_CHANGES_PER_PR${NC} lines"
echo -e "  ${GREEN}Period:${NC} ${BOLD}$DAYS_DIFF${NC} days"

if [ "$DAYS_DIFF" -gt 0 ]; then
    AUTHORED_PER_WEEK=$(echo "scale=1; $TOTAL_AUTHORED * 7 / $DAYS_DIFF" | bc)
    REVIEWED_PER_WEEK=$(echo "scale=1; $TOTAL_REVIEWED * 7 / $DAYS_DIFF" | bc)
    echo -e "  ${GREEN}Average PRs Created per Week:${NC} ${BOLD}$AUTHORED_PER_WEEK${NC}"
    echo -e "  ${GREEN}Average PRs Reviewed per Week:${NC} ${BOLD}$REVIEWED_PER_WEEK${NC}"
fi

echo ""

# ============================================================================
# ALL REPOSITORIES INVOLVED
# ============================================================================
echo -e "${BOLD}${BLUE}📂 All Repositories You Interacted With${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

ALL_REPOS=$(echo "$AUTHORED_PRS $REVIEWED_PRS" | jq -s 'add | [.[] | .repository.nameWithOwner] | unique | sort')
TOTAL_REPOS=$(echo "$ALL_REPOS" | jq 'length')

echo -e "  ${GREEN}Total Repositories:${NC} ${BOLD}$TOTAL_REPOS${NC}"
echo "$ALL_REPOS" | jq -r '.[] | "    • \(.)"'
echo ""

# ============================================================================
# EXPORT OPTION
# ============================================================================
echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║  Summary complete!${NC}"
echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}💡 Tip: You can export detailed data with:${NC}"
echo -e "   ${CYAN}# Authored PRs:${NC}"
echo -e "   gh search prs --author=@me --created=\"${START_DATE}..${END_DATE}\" --json number,title,state,repository,url > authored_prs.json"
echo -e ""
echo -e "   ${CYAN}# Save this summary:${NC}"
echo -e "   ./github-activity-summary.sh $START_DATE $END_DATE > my_github_summary.txt"
echo ""
