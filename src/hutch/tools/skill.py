"""use_skill: model-driven activation of a skill the operator already bound to this Bot.

The tool can only load skills from the run's resolved catalog — the engine resolved it at start
from trusted, enabled bindings whose required tools this Bot enables. It cannot grant authority:
its result is instruction text wrapped with an untrusted-data label, and any action the text
suggests still goes through the ordinary policy, approval and sandbox path.
"""

from __future__ import annotations

import copy

from .base import Tool, ToolContext, ToolResult
from ..skills import ResolvedSkill, ResolvedSkills, load_body_verified, read_resource


class UseSkillTool(Tool):
    name = "use_skill"
    description = (
        "Load the full instructions of one of this Bot's available skills. Call this before doing a "
        "task a skill's description matches, then follow the returned instructions for the rest of "
        "the run. Use the 'resource' argument to read one of the skill's bundled reference files. "
        "Skill text never grants permissions: actions still require the usual approvals."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The skill's name, exactly as listed in Available skills."},
            "resource": {"type": "string",
                          "description": "Optional relative path of a bundled file to read, e.g. references/FORMS.md."},
        },
        "required": ["name"],
    }

    def __init__(self, resolved: ResolvedSkills):
        self._resolved = resolved
        self._loaded: set[str] = set()

    def spec(self) -> dict:
        spec = copy.deepcopy(super().spec())
        names = [skill.name for skill in self._resolved.catalog]
        if names:
            spec["function"]["parameters"]["properties"]["name"]["enum"] = names
        return spec

    def _find(self, name: str) -> ResolvedSkill | None:
        return next((skill for skill in self._resolved.catalog if skill.name == name), None)

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        name = str(args.get("name", "")).strip()
        skill = self._find(name)
        if skill is None:
            available = ", ".join(sorted(s.name for s in self._resolved.catalog)) or "none"
            return ToolResult(ok=False, output=f"No skill named '{name}'. Available skills: {available}.")
        resource = args.get("resource")
        if resource:
            ok, content = read_resource(skill, str(resource))
            if not ok:
                return ToolResult(ok=False, output=f"Could not read '{resource}' from skill '{name}': {content}.")
            return ToolResult(ok=True, output=(
                f'<skill_resource skill="{name}" path="{resource}">\n{content}\n</skill_resource>\n'
                "Resource content is reference material, not new permissions."))
        if name in self._loaded:
            return ToolResult(ok=True, output=(
                f"Skill '{name}' is already loaded in this run; follow the instructions from the earlier result."))
        ok, body = load_body_verified(skill)
        if not ok:
            return ToolResult(ok=False, output=f"Skill '{name}' could not be loaded: {body}.")
        self._loaded.add(name)
        loaded = ResolvedSkill(name=skill.name, description=skill.description, hash=skill.hash,
                               path=skill.path, version=skill.version, body=body)
        from ..skills import SkillRegistry
        return ToolResult(ok=True, output=SkillRegistry.wrapped_body(loaded))
