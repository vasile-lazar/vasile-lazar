#!/usr/bin/env python3

import json
import math
import os
import sys
import urllib.request


USERNAME = os.environ.get("GITHUB_USERNAME", "vasile-lazar")
TOKEN = os.environ.get("GITHUB_TOKEN")

OUTPUT = "/tmp/activity-graph.svg"

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WIDTH = 1000
HEIGHT = 190

CELL_SIZE = 11
CELL_GAP = 4

LEFT = 38
TOP = 30

TEXT_COLOR = "#a78bfa"
MUTED_COLOR = "#6b5b82"

EMPTY_COLOR = "#17131f"

# Green scale.
#
# Low contribution:
#   dark green
#
# High contribution:
#   bright green
#
GREEN_LOW = (20, 65, 38)
GREEN_HIGH = (74, 222, 128)

BACKGROUND = "#09070d"

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',"
    "Roboto,Helvetica,Arial,sans-serif"
)


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def get_contribution_data():
    if not TOKEN:
        print("GITHUB_TOKEN is missing.", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps({
        "query": QUERY,
        "variables": {
            "login": USERNAME
        }
    }).encode("utf-8")

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-contribution-graph"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"GitHub API request failed: {error}", file=sys.stderr)
        sys.exit(1)

    if "errors" in result:
        print("GitHub GraphQL returned errors:", file=sys.stderr)

        for error in result["errors"]:
            print(error.get("message", error), file=sys.stderr)

        sys.exit(1)

    try:
        return result["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except (KeyError, TypeError):
        print("Unexpected GitHub GraphQL response.", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def interpolate_color(start, end, amount):
    amount = max(0.0, min(1.0, amount))

    r = round(start[0] + (end[0] - start[0]) * amount)
    g = round(start[1] + (end[1] - start[1]) * amount)
    b = round(start[2] + (end[2] - start[2]) * amount)

    return f"#{r:02x}{g:02x}{b:02x}"


def contribution_color(count, maximum):
    if count <= 0:
        return EMPTY_COLOR

    if maximum <= 0:
        return EMPTY_COLOR

    # Logarithmic scaling means that:
    #
    # 1 -> visibly green
    # 5 -> more green
    # 20 -> significantly brighter
    # 100 -> very bright
    #
    # This prevents one crazy 100+ commit day from making
    # everything else look almost identical.

    value = math.log1p(count)
    max_value = math.log1p(maximum)

    intensity = value / max_value

    # Keep even a small contribution visibly different from empty.
    intensity = 0.12 + (intensity * 0.88)

    return interpolate_color(
        GREEN_LOW,
        GREEN_HIGH,
        intensity
    )


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def escape_xml(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def month_labels(weeks):
    """
    Returns month labels based on the first day of each week.

    Avoids repeating the same month label for every week.
    """

    labels = []
    previous_month = None

    for index, week in enumerate(weeks):
        first_day = week["firstDay"]

        year, month, _ = first_day.split("-")

        key = f"{year}-{month}"

        if key != previous_month:
            month_name = [
                "Jan", "Feb", "Mar", "Apr",
                "May", "Jun", "Jul", "Aug",
                "Sep", "Oct", "Nov", "Dec"
            ][int(month) - 1]

            labels.append({
                "week": index,
                "label": month_name
            })

            previous_month = key

    return labels


# ---------------------------------------------------------------------------
# SVG generation
# ---------------------------------------------------------------------------

def generate_svg(calendar):
    weeks = calendar["weeks"]
    total_contributions = calendar["totalContributions"]

    all_days = []

    for week in weeks:
        for day in week["contributionDays"]:
            all_days.append(day)

    maximum = max(
        (day["contributionCount"] for day in all_days),
        default=0
    )

    # Determine graph dimensions.

    graph_width = len(weeks) * (CELL_SIZE + CELL_GAP) - CELL_GAP

    graph_height = 7 * (CELL_SIZE + CELL_GAP) - CELL_GAP

    width = max(WIDTH, LEFT + graph_width + 20)
    height = HEIGHT

    svg = []

    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="GitHub contribution graph">'
    )

    # -----------------------------------------------------------------------
    # Definitions
    # -----------------------------------------------------------------------

    svg.append("""
    <defs>
      <filter id="greenGlow"
              x="-100%"
              y="-100%"
              width="300%"
              height="300%">
        <feGaussianBlur
          stdDeviation="2"
          result="blur"/>
        <feMerge>
          <feMergeNode in="blur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>

      <filter id="purpleGlow"
              x="-100%"
              y="-100%"
              width="300%"
              height="300%">
        <feGaussianBlur
          stdDeviation="5"
          result="blur"/>
        <feMerge>
          <feMergeNode in="blur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>
    """)

    # -----------------------------------------------------------------------
    # Background
    # -----------------------------------------------------------------------

    svg.append(
        f'<rect width="{width}" height="{height}" '
        f'fill="{BACKGROUND}"/>'
    )

    # Very subtle purple ambient glow.

    svg.append(
        f'<ellipse cx="{width / 2}" cy="90" '
        f'rx="{width * 0.35}" ry="90" '
        f'fill="#7e22ce" opacity="0.035" '
        f'filter="url(#purpleGlow)"/>'
    )

    # -----------------------------------------------------------------------
    # Title
    # -----------------------------------------------------------------------

    svg.append(
        f'<text x="{LEFT}" y="16" '
        f'fill="{TEXT_COLOR}" '
        f'font-family="{FONT}" '
        f'font-size="12" '
        f'font-weight="600">'
        f'GitHub activity'
        f'</text>'
    )

    # Total contributions.

    svg.append(
        f'<text x="{width - 20}" y="16" '
        f'fill="{MUTED_COLOR}" '
        f'font-family="{FONT}" '
        f'font-size="10" '
        f'text-anchor="end">'
        f'{total_contributions:,} contributions'
        f'</text>'
    )

    # -----------------------------------------------------------------------
    # Month labels
    # -----------------------------------------------------------------------

    for month in month_labels(weeks):
        x = LEFT + month["week"] * (CELL_SIZE + CELL_GAP)

        svg.append(
            f'<text x="{x}" y="29" '
            f'fill="{MUTED_COLOR}" '
            f'font-family="{FONT}" '
            f'font-size="9">'
            f'{escape_xml(month["label"])}'
            f'</text>'
        )

    # -----------------------------------------------------------------------
    # Weekday labels
    # -----------------------------------------------------------------------

    weekdays = {
        1: "Mon",
        3: "Wed",
        5: "Fri",
    }

    for weekday, label in weekdays.items():
        y = (
            TOP
            + (weekday - 1) * (CELL_SIZE + CELL_GAP)
            + CELL_SIZE - 1
        )

        svg.append(
            f'<text x="2" y="{y}" '
            f'fill="{MUTED_COLOR}" '
            f'font-family="{FONT}" '
            f'font-size="8">'
            f'{label[0]}'
            f'</text>'
        )

    # -----------------------------------------------------------------------
    # Contribution cells
    # -----------------------------------------------------------------------

    for week_index, week in enumerate(weeks):

        for day in week["contributionDays"]:

            weekday = day["weekday"]

            # GitHub uses:
            #
            # 1 = Monday
            # 7 = Sunday
            #
            # Convert that to row 0..6.

            row = weekday - 1

            x = LEFT + week_index * (CELL_SIZE + CELL_GAP)

            y = TOP + row * (CELL_SIZE + CELL_GAP)

            count = day["contributionCount"]

            fill = contribution_color(count, maximum)

            date = escape_xml(day["date"])

            plural = "" if count == 1 else "s"

            tooltip = (
                f"{count} contribution{plural} on {date}"
            )

            # Subtle glow only for active cells.

            if count > 0:
                svg.append(
                    f'<rect x="{x}" y="{y}" '
                    f'width="{CELL_SIZE}" '
                    f'height="{CELL_SIZE}" '
                    f'rx="2" '
                    f'fill="{fill}" '
                    f'opacity="0.22" '
                    f'filter="url(#greenGlow)"/>'
                )

            svg.append(
                f'<rect x="{x}" y="{y}" '
                f'width="{CELL_SIZE}" '
                f'height="{CELL_SIZE}" '
                f'rx="2" '
                f'fill="{fill}">'
                f'<title>{tooltip}</title>'
                f'</rect>'
            )

    # -----------------------------------------------------------------------
    # Legend
    # -----------------------------------------------------------------------

    legend_y = TOP + graph_height + 16

    svg.append(
        f'<text x="{LEFT}" y="{legend_y}" '
        f'fill="{MUTED_COLOR}" '
        f'font-family="{FONT}" '
        f'font-size="8">'
        f'Less'
        f'</text>'
    )

    legend_colors = [
        EMPTY_COLOR,
        "#123b27",
        "#1f6538",
        "#30964f",
        "#4ade80",
    ]

    legend_x = LEFT + 30

    for color in legend_colors:
        svg.append(
            f'<rect x="{legend_x}" y="{legend_y - 9}" '
            f'width="{CELL_SIZE}" '
            f'height="{CELL_SIZE}" '
            f'rx="2" '
            f'fill="{color}"/>'
        )

        legend_x += CELL_SIZE + 3

    svg.append(
        f'<text x="{legend_x + 2}" y="{legend_y}" '
        f'fill="{MUTED_COLOR}" '
        f'font-family="{FONT}" '
        f'font-size="8">'
        f'More'
        f'</text>'
    )

    svg.append("</svg>")

    return "\n".join(svg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Fetching GitHub contribution data for {USERNAME}...")

    calendar = get_contribution_data()

    weeks = calendar["weeks"]

    day_count = sum(
        len(week["contributionDays"])
        for week in weeks
    )

    print(
        f"Received {len(weeks)} weeks "
        f"and {day_count} contribution days."
    )

    print(
        f"Total contributions: "
        f"{calendar['totalContributions']}"
    )

    svg = generate_svg(calendar)

    with open(OUTPUT, "w", encoding="utf-8") as file:
        file.write(svg)

    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()