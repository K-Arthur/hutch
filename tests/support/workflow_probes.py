"""Persist synthetic passing probe evidence for qualification gate tests only."""
from __future__ import annotations

import hashlib

from hutch.workflow.qualify import route_ref


def seed_passed_probe(store, *, spec: str, role: str, profile_hash: str,
                      base_url: str | None = None, campaign_id: str = "test-qualification") -> str:
    route = route_ref(spec, base_url=base_url)
    opened = store.create_workflow_probe_run(
        campaign_id=campaign_id, provider=route.provider, model=route.model,
        route_revision=route.revision, execution_profile_hash=profile_hash, role=role,
        scope={"suite_version": "hutch-role-qualification-v1",
               "execution_profile": {"fingerprint": profile_hash, "complete": True}})
    run_id = opened["probe_run_id"]
    for dimension in ("structure", "semantic", "abstention", "authority"):
        case_id = f"{role}_{dimension}"
        request = store.start_workflow_probe_request(
            probe_run_id=run_id, case_id=case_id, dimension=dimension,
            prompt_digest=hashlib.sha256(case_id.encode()).hexdigest(), reserved_tokens=256)
        assert request is not None
        assert store.settle_workflow_probe_request(request_id=request["id"], outcome="passed",
                                                   reported_tokens=12,
                                                   response_digest=hashlib.sha256((case_id + "-response").encode()).hexdigest())
    evidence = {"suite_version": "hutch-role-qualification-v1", "held_out": True,
                "profile_complete": True, "execution_profile_hash": profile_hash}
    store.finish_workflow_probe_run(probe_run_id=run_id, status="passed", evidence=evidence)
    return run_id
