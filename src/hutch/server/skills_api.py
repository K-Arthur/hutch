"""Agent Skills management API + the shared readiness resolver endpoint.

All routes here inherit the app-level remote authorization, so paired phones are refused by the
default-deny inventory, skills are owner configuration, like connections and schedules.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..skills import MAX_SKILLS_PER_BOT, SkillError, SkillRegistry


class SkillInstallRequest(BaseModel):
    source: Literal["path", "builtin"]
    path: Optional[str] = Field(default=None, max_length=4096)
    name: Optional[str] = Field(default=None, max_length=64)


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

    @app.get("/api/v1/skills/{name}")
    def skill_detail(name: str) -> dict:
        detail = skill_or_404(name)
        detail["bound_bots"] = [
            {"id": bot.id, "name": bot.name, "display_name": bot.display_name}
            for bot in store.list_bots() if name in (bot.skills or [])
        ]
        detail["limits"] = {"max_skills_per_bot": MAX_SKILLS_PER_BOT}
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
