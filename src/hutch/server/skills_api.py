"""Agent Skills management API + the shared readiness resolver endpoint.

All routes here inherit the app-level remote authorization, so paired phones are refused by the
default-deny inventory, skills are owner configuration, like connections and schedules.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..skills import MAX_SKILLS_PER_BOT, SkillError, SkillRegistry
from ..skill_scan import scan_package
from ..skill_update import compare_packages


class SkillInstallRequest(BaseModel):
    source: Literal["path", "builtin"]
    path: Optional[str] = Field(default=None, max_length=4096)
    name: Optional[str] = Field(default=None, max_length=64)


class SkillFetchRequest(BaseModel):
    """A published package to download. Fetching is install-at-a-distance, never trust."""

    url: str = Field(min_length=1, max_length=4096)
    replace: bool = False


class RegistryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=32)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="", max_length=80)


class RegistryInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    replace: bool = False


def install_skills_routes(app: FastAPI, store, config) -> None:
    def registry() -> SkillRegistry:
        return SkillRegistry(config.state_dir)

    def skill_or_404(name: str):
        detail = registry().detail(name, include_body=True)
        if detail is None:
            raise HTTPException(404, f"no such installed skill: {name}")
        return detail

    @app.get("/api/v1/skills")
    def list_skills(workspace: Optional[str] = Query(default=None, max_length=4096)) -> dict:
        """Installed skills, discovered candidates, collisions and scan diagnostics (bounded)."""
        return registry().library(workspace=workspace)

    # -- configured registries: discovery only; nothing here installs implicitly -------------

    def index_client():
        from ..skill_registry_index import RegistryIndex
        return RegistryIndex(store.config.state_dir)

    @app.get("/api/v1/skills/registries")
    def list_registries() -> dict:
        client = index_client()
        catalog = client.catalog()
        return {"registries": client.configured(), "read": [state.__dict__ for state in catalog.states],
                "note": catalog.to_dict()["note"]}

    @app.post("/api/v1/skills/registries", status_code=201)
    def add_registry(body: RegistryRequest) -> dict:
        from ..skill_registry_index import RegistryError
        try:
            return index_client().add(body.id, body.url, title=body.title)
        except RegistryError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.delete("/api/v1/skills/registries/{registry_id}")
    def remove_registry(registry_id: str) -> dict:
        return {"removed": index_client().remove(registry_id)}

    @app.get("/api/v1/skills/available")
    def available_skills() -> dict:
        """What the configured registries list, annotated with what is already installed."""
        installed = {entry["name"] for entry in registry().library().get("skills", [])}
        return index_client().catalog().to_dict(installed=installed)

    @app.post("/api/v1/skills/registries/install", status_code=201)
    def install_from_registry(body: RegistryInstallRequest) -> dict:
        """Install one listed package, verifying the digest the registry published."""
        from ..skill_registry_index import RegistryError
        try:
            return index_client().install(registry(), body.name, replace=body.replace)
        except RegistryError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.get("/api/v1/skills/{name}")
    def skill_detail(name: str) -> dict:
        detail = skill_or_404(name)
        detail["bound_bots"] = [
            {"id": bot.id, "name": bot.name, "display_name": bot.display_name}
            for bot in store.list_bots() if name in (bot.skills or [])
        ]
        detail["limits"] = {"max_skills_per_bot": MAX_SKILLS_PER_BOT}
        # Content review is shown wherever a package is reviewed, including before trust. It is
        # advisory: it never grants trust and never blocks an owner's decision.
        if detail.get("directory"):
            detail["scan"] = scan_package(detail["directory"])
        # A staged update is a write path. Say what applying it would change, not just that a
        # different hash is waiting: new requirements are the difference between reviewing and
        # rubber-stamping.
        staged = detail.get("staged_update") or {}
        if staged.get("path"):
            detail["staged_changes"] = compare_packages(detail.get("directory", ""), staged["path"])
        return detail

    @app.post("/api/v1/skills/install", status_code=201)
    def install_skill(body: SkillInstallRequest) -> dict:
        try:
            if body.source == "builtin":
                if not body.name:
                    raise SkillError("a bundled skill name is required")
                return registry().install_builtin(body.name)
            if not body.path:
                raise SkillError("a local directory path is required")
            return registry().install_path(body.path)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/fetch", status_code=201)
    def fetch_skill(body: SkillFetchRequest) -> dict:
        """Install a package published at a URL. It lands untrusted, with its provenance recorded."""
        from ..skill_remote import install_from_url
        try:
            return install_from_url(registry(), body.url, replace=body.replace)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.get("/api/v1/skills/{name}/dependencies")
    def skill_dependencies(name: str) -> dict:
        """What this skill depends on, what is missing, and where each missing one is listed."""
        skill_or_404(name)
        from ..skill_dependency import resolve_dependencies
        return resolve_dependencies(registry(), name, index=index_client())

    @app.post("/api/v1/skills/{name}/trust")
    def trust_skill(name: str) -> dict:
        try:
            return registry().trust(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/enable")
    def enable_skill(name: str) -> dict:
        try:
            return registry().enable(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/disable")
    def disable_skill(name: str) -> dict:
        try:
            return registry().disable(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/recheck")
    def recheck_skill(name: str) -> dict:
        try:
            return registry().recheck(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/update")
    def update_skill(name: str) -> dict:
        try:
            return registry().update(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/update/apply")
    def apply_skill_update(name: str) -> dict:
        try:
            return registry().apply_update(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/update/discard")
    def discard_skill_update(name: str) -> dict:
        try:
            return registry().discard_update(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.post("/api/v1/skills/{name}/rollback")
    def rollback_skill(name: str) -> dict:
        try:
            return registry().rollback(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.delete("/api/v1/skills/{name}")
    def uninstall_skill(name: str) -> dict:
        try:
            return registry().uninstall(name)
        except SkillError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    @app.get("/api/v1/bots/{ref}/readiness")
    def bot_readiness_route(ref: str) -> dict:
        from ..readiness import bot_readiness

        bot = store.get_bot(ref)
        if bot is None:
            raise HTTPException(404, f"no such bot: {ref}")
        return bot_readiness(store, config, bot)
