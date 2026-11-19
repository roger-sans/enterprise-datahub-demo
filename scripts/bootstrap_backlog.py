"""Initialise milestones and issues from the demo's delivery baseline."""

import argparse
import json
from pathlib import Path
import subprocess

PORTFOLIO = Path(__file__).resolve().parents[1] / "hub/contracts/delivery.json"
EXPECTED_REPO = "roger-sans/enterprise-datahub-demo"


def gh(endpoint, payload=None, method="POST", paginate=False):
    command = ["gh", "api", endpoint]
    if payload is not None:
        command.extend(["--method", method, "--input", "-"])
    if paginate:
        command.extend(["--paginate", "--slurp"])
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, check=True)
    decoded = json.loads(result.stdout)
    return [entry for page in decoded for entry in page] if paginate else decoded


def body(item):
    dependencies = ", ".join(item["depends"]) or "None"
    return (
        f"**{item['kind']} · {item['owner']}**\n\n{item['story']}\n\n"
        f"### Acceptance criteria\n\n{item['acceptance']}\n\n"
        f"### Delivery signals\n\n- Priority score: {item['score']} "
        f"(value {item['value']}, risk reduction {item['risk']}, effort {item['effort']})\n"
        f"- Depends on: {dependencies}\n- Evidence: {item['evidence']}\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Make authenticated writes with the GitHub CLI.")
    args = parser.parse_args()
    baseline = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    if not args.apply:
        print(f"{len(baseline['milestones'])} milestones and {len(baseline['items'])} issues ready for {EXPECTED_REPO}.")
        return
    api_path = f"repos/{EXPECTED_REPO}"
    existing = {item["title"]: item for item in gh(f"{api_path}/milestones?state=all&per_page=100", paginate=True)}
    milestones = []
    for record in baseline["milestones"]:
        title = record["title"]
        milestones.append(existing.get(title) or gh(f"{api_path}/milestones", {
            "title": title, "description": record["goal"] + "\n\nExit: " + record["exit"],
        }))
    issues = gh(f"{api_path}/issues?state=all&per_page=100", paginate=True)
    for item in sorted(baseline["items"], key=lambda i: (i["milestone"], -i["score"])):
        prefix = f"[{item['id']}] "
        if any(issue["title"].startswith(prefix) and "pull_request" not in issue for issue in issues):
            continue
        issue = gh(f"{api_path}/issues", {"title": prefix + item["title"], "body": body(item),
                                        "milestone": milestones[item["milestone"]]["number"]})
        print(issue["html_url"])
        if item["status"] == "published":
            gh(f"{api_path}/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"}, method="PATCH")
    for record, milestone in zip(baseline["milestones"], milestones, strict=True):
        if record["state"] == "published" and milestone["state"] == "open":
            gh(f"{api_path}/milestones/{milestone['number']}", {"state": "closed"}, method="PATCH")


if __name__ == "__main__":
    main()
