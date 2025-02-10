import base64
from collections import defaultdict
from datetime import datetime

import click
import requests


def format_timestamp(dt_str: str) -> str:
    """Convert GitHub timestamp to readable format."""
    return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")


def get_line_content(
    session: requests.Session, owner: str, repo: str, path: str, comment: dict
) -> tuple[str, bool]:
    """Get the line content, handling both current and outdated comments."""
    is_outdated = False
    line_content = "No content available"

    # For outdated comments, GitHub provides the diff context
    if "diff_hunk" in comment:
        is_outdated = True
        # Extract the specific line from the diff hunk
        diff_lines = comment["diff_hunk"].split("\n")
        # The last line in the diff hunk is typically the one being commented on
        if diff_lines:
            line_content = diff_lines[-1].lstrip("+-").strip()
        return line_content, is_outdated

    # For current comments, get the line from the file
    try:
        line_number = comment.get("line", comment.get("original_line"))
        if not line_number:
            return "No line number available", False

        url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={comment["commit_id"]}'
        response = session.get(url)
        response.raise_for_status()

        content = base64.b64decode(response.json()["content"]).decode("utf-8")
        lines = content.split("\n")

        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip(), False
        return "Line not found", False
    except Exception as e:
        return f"Could not fetch line content: {e!s}", False


def process_review_comments(
    review_comments: list, session: requests.Session, owner: str, repo: str
) -> tuple[list, dict]:
    """Process review comments and organize them into threads."""
    review_threads = defaultdict(list)
    standalone_reviews = []

    for comment in review_comments:
        if "in_reply_to_id" in comment:
            review_threads[comment["in_reply_to_id"]].append(comment)
        else:
            standalone_reviews.append(comment)

    return standalone_reviews, review_threads


def process_general_comments(issue_comments: list) -> tuple[list, dict]:
    """Process general comments and organize them into threads."""
    general_threads = defaultdict(list)
    general_comments = []

    for comment in issue_comments:
        if "in_reply_to" in comment:
            general_threads[comment["in_reply_to"]].append(comment)
        else:
            general_comments.append(comment)

    return general_comments, general_threads


@click.command()
@click.argument("pr_url")
@click.option("-o", "--output", default="pr_comments.md", help="Output file path")
def from_github_comments(pr_url: str, output: str) -> None:
    """Fetch comments from a public GitHub PR and save them as markdown."""
    # Parse PR URL
    parts = pr_url.strip("/").split("/")
    try:
        gh_index = parts.index("github.com")
        owner = parts[gh_index + 1]
        repo = parts[gh_index + 2]
        pr_num = parts[gh_index + 4]
    except (ValueError, IndexError) as e:
        click.echo("Invalid GitHub PR URL", err=True)
        raise click.Exit(1) from e

    # Setup session
    session = requests.Session()
    session.headers["Accept"] = "application/vnd.github.v3+json"
    base_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        # Get PR details
        pr = session.get(f"{base_url}/pulls/{pr_num}").json()

        # Get both types of comments
        review_comments = session.get(f"{base_url}/pulls/{pr_num}/comments").json()
        issue_comments = session.get(f"{base_url}/issues/{pr_num}/comments").json()

        # Process comments into threads
        standalone_reviews, review_threads = process_review_comments(
            review_comments, session, owner, repo
        )
        general_comments, general_threads = process_general_comments(issue_comments)

        # Generate markdown
        markdown = [
            f"# PR Comments: {owner}/{repo}#{pr_num}",
            f"\n**Title**: {pr['title']}",
            f"**Author**: {pr['user']['login']}",
            f"**Created**: {format_timestamp(pr['created_at'])}\n",
        ]

        # Add review comments with their threads
        if review_comments:
            markdown.append("\n## Code Review Comments\n")

            # Process each standalone comment and its replies
            for comment in standalone_reviews:
                # Get the line content and outdated status
                line_content, is_outdated = get_line_content(
                    session, owner, repo, comment["path"], comment
                )
                line_number = comment.get("line", comment.get("original_line", "Unknown"))
                line_number = line_number or "Unknown"
                line_str = "(Outdated)" if is_outdated else f"Line {line_number}"
                body = comment["body"].replace("\r\n", " ")

                markdown.extend(
                    [
                        f"* File `{comment['path']}`, {line_str}:",
                        "  ```",
                        f"  {line_content}",
                        "  ```",
                        f"  * {comment['user']['login']}, {format_timestamp(comment['created_at'])}:",
                        f"    {body}",
                    ]
                )

                # Add any replies to this comment
                for reply in review_threads.get(comment["id"], []):
                    body = reply["body"].replace("\r\n", " ")
                    markdown.extend(
                        [
                            f"    * {reply['user']['login']}, {format_timestamp(reply['created_at'])}:",
                            f"      {body}",
                        ]
                    )
                markdown.append("")  # Empty line between comment threads

        # Add general comments with their threads
        if issue_comments:
            markdown.append("\n## General Comments\n")

            for comment in general_comments:
                body = comment["body"].replace("\r\n", " ")
                markdown.extend(
                    [
                        f"* {comment['user']['login']}, {format_timestamp(comment['created_at'])}:",
                        f"  {body}",
                    ]
                )

                # Add any replies to this comment
                for reply in general_threads.get(comment["id"], []):
                    body = reply["body"].replace("\r\n", " ")
                    markdown.extend(
                        [
                            f"  * {reply['user']['login']}, {format_timestamp(reply['created_at'])}:",
                            f"    {body}",
                        ]
                    )
                markdown.append("")  # Empty line between comment threads

        # Write to file
        with open(output, "w", encoding="utf-8") as f:
            f.write("\n".join(markdown))

        click.echo(f"Comments exported to {output}")

    except requests.RequestException as e:
        click.echo(f"Error accessing GitHub API: {e}", err=True)
        raise click.Exit(1) from e
    except KeyError as e:
        click.echo(f"Error parsing GitHub response: {e}", err=True)
        raise click.Exit(1) from e


if __name__ == "__main__":
    from_github_comments()
