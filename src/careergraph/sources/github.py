"""Public GitHub profile -> ProfileDocuments (one per non-fork repository).

Endpoints (verified in GitHub REST docs, 2026-11-22): GET /users/{user}/repos,
GET /repos/{owner}/{repo}/languages, GET /repos/{owner}/{repo}/readme with
Accept: application/vnd.github.raw+json. Unauthenticated limit: 60 requests/hour.
"""

from __future__ import annotations

from typing import Any

from careergraph.domain.models import ProfileDocument
from careergraph.security.fetcher import FetchError, SafeFetcher
from careergraph.sources.documents import sha256

API = "https://api.github.com"
API_VERSION = "2022-11-28"  # long-term supported version (supported until 2028-03-10)


class GitHubAdapter:
    """Reads repositories, languages, topics and truncated READMEs through SafeFetcher."""

    def __init__(self, fetcher: SafeFetcher, token: str | None) -> None:
        self.fetcher, self.token = fetcher, token

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        h = {"Accept": accept, "X-GitHub-Api-Version": API_VERSION}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _json(self, path: str) -> Any:
        return self.fetcher.get(API + path, headers=self._headers()).json()

    def fetch_profile(
        self, username: str, max_repos: int, readme_chars: int
    ) -> list[ProfileDocument]:
        """Return one document per non-fork, non-archived repo, most recently pushed first."""
        repos = self._json(
            f"/users/{username}/repos?type=owner&sort=pushed&direction=desc&per_page=100"
        )
        picked = [r for r in repos if not r.get("fork") and not r.get("archived")][:max_repos]
        return [self._document(r, readme_chars) for r in picked]

    def _document(self, repo: dict[str, Any], readme_chars: int) -> ProfileDocument:
        full = repo["full_name"]
        langs: dict[str, int] = self._json(f"/repos/{full}/languages")
        total = sum(langs.values()) or 1
        lang_text = ", ".join(
            f"{k} ({100 * v // total}%)" for k, v in sorted(langs.items(), key=lambda kv: -kv[1])
        )
        readme = ""
        if readme_chars:
            try:
                resp = self.fetcher.get(
                    f"{API}/repos/{full}/readme",
                    headers=self._headers("application/vnd.github.raw+json"),
                )
                readme = resp.text()[:readme_chars]
            except FetchError:
                readme = ""
        text = "\n".join([
            f"Repository: {repo['name']}",
            f"Description: {repo.get('description') or ''}",
            f"URL: {repo['html_url']}",
            f"Languages: {lang_text}",
            f"Topics: {', '.join(repo.get('topics') or [])}",
            f"Stars: {repo.get('stargazers_count', 0)}",
            f"Last push: {(repo.get('pushed_at') or '')[:10]}",
            "",
            "README (truncated):",
            readme,
        ])  # fmt: skip
        return ProfileDocument(
            source_id=f"github:{full}",
            kind="github_repo",
            title=repo["name"],
            text=text,
            content_hash=sha256(text),
            uri=repo["html_url"],
        )
