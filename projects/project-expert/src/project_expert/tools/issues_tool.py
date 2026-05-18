from typing import Any

from project_expert.config import Config
from project_expert.exceptions import UpstreamUnavailable
from project_expert.state import State


def projects_issues(
    *,
    config: Config,
    state: State,
    issues_client: Any,
    project: str,
    query: str,
    state_filter: str = "open",
    limit: int = 20,
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    try:
        results = issues_client.search(repo=proj.repo, query=query, state=state_filter, limit=limit)
    except UpstreamUnavailable as exc:
        return {"error": "upstream_unavailable", "message": str(exc)}
    return [r.model_dump() for r in results]
