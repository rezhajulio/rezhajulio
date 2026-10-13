#!/usr/bin/env python3
"""Refresh the auto-updated sections of README.md.

- Latest blog posts: parsed from https://rezhajul.io/rss.xml
- Open-source contributions: latest merged PRs authored by rezhajulio
  to repositories he does not own (GitHub search API).

Sections are delimited by HTML comment markers in README.md; everything
between a START/END pair is replaced. Run daily from CI; exits non-zero
on fetch failure so a broken feed or API is noticed instead of silently
going stale.
"""

import html
import json
import os
import re
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
BLOG_FEED = "https://rezhajul.io/rss.xml"
GITHUB_USER = "rezhajulio"
MAX_ITEMS = 5

BLOG_START = "<!-- BLOG-POSTS:START -->"
BLOG_END = "<!-- BLOG-POSTS:END -->"
PR_START = "<!-- CONTRIBUTIONS:START -->"
PR_END = "<!-- CONTRIBUTIONS:END -->"


def fetch_blog_posts():
    req = urllib.request.Request(BLOG_FEED, headers={"User-Agent": "readme-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml = resp.read().decode("utf-8")
    posts = []
    for item in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        body = item.group(1)
        title = html.unescape(re.search(r"<title>(.*?)</title>", body, re.S).group(1))
        link = re.search(r"<link>(.*?)</link>", body, re.S).group(1)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", body, re.S).group(1)
        date = parsedate_to_datetime(pub).strftime("%b %d, %Y")
        posts.append(f"- [{title}]({link}) — {date}")
        if len(posts) == MAX_ITEMS:
            break
    if not posts:
        raise RuntimeError("no blog posts parsed from RSS feed")
    return posts


def fetch_merged_prs(token):
    query = f"author:{GITHUB_USER}+type:pr+is:merged"
    url = (
        "https://api.github.com/search/issues"
        f"?q={query}&sort=updated&order=desc&per_page=20"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "readme-updater",
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    prs = []
    for item in data.get("items", []):
        owner, name = item["repository_url"].rsplit("/", 2)[-2:]
        if owner.lower() == GITHUB_USER.lower():
            continue  # only contributions to other people's projects
        merged = datetime.fromisoformat(
            item["closed_at"].replace("Z", "+00:00")
        ).strftime("%b %d, %Y")
        prs.append(
            f"- [{owner}/{name}#{item['number']}]({item['html_url']})"
            f" — {item['title']} ({merged})"
        )
        if len(prs) == MAX_ITEMS:
            break
    return prs


def replace_section(text, start, end, lines):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise RuntimeError(f"markers {start} / {end} not found in README.md")
    return pattern.sub(f"{start}\n" + "\n".join(lines) + f"\n{end}", text)


def main():
    text = README.read_text()
    text = replace_section(text, BLOG_START, BLOG_END, fetch_blog_posts())
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        text = replace_section(text, PR_START, PR_END, fetch_merged_prs(token))
    README.write_text(text)


if __name__ == "__main__":
    main()
