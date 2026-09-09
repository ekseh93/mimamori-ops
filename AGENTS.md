# Mimamori Ops collaboration rules

The user authorized public publication and normal GitHub collaboration for `ekseh93/mimamori-ops` on 2026-09-10. Continue authorized repository work without asking again for each local edit, commit, branch push, Issue, draft PR, or clearly labeled AI review. AWS deployment, billing, credentials and unrelated publication need their own scope confirmation.

## Work cadence

- Read the relevant Issue, `CONTRIBUTING.md`, and role packet before changing code.
- Work on a short-lived `codex/<issue>-<purpose>` branch from current `origin/main`; never push feature work directly to main.
- Commit after each coherent, reviewable unit: implementation with focused tests, a tested fix, or relevant documentation. Push that branch at the same milestone so progress is visible. Do not commit every keystroke or wait until a large session ends.
- Open a draft PR early and link the Issue. Update it when scope changes. Close issues through a verified merge, not an unverified claim.
- Use explicit paths when staging. Exclude credentials, Terraform state, build outputs, local task IDs, machine paths and `docs/pipeline/registry.json`.
- Run `python scripts/check_public_content.py` and checks appropriate to the change before publishing. `python -m unittest discover -s tests -v` must run with dev dependencies for all AWS mock tests.
- On a complete feature, get an independent Sol review of the exact HEAD, wait for required GitHub checks, and merge using the approved repository workflow. Do not bypass protection or force-push main.
- User instructions override these project conventions. Preserve unrelated changes and existing approvals.

## Models and handoff

- Design and risk decisions: Sol High. Bounded implementation and its tests: Luna High. Independent verification: Sol High.
- Role branches and local task routing are in the ignored `docs/pipeline/registry.json` in the original workspace. Never add that file to Git.
- Use `docs/07-model-pipeline.ko.md` for packet/HEAD handoffs. A design marker is an internal readiness signal, not a request for the user to reapprove each safe edit.
- Pass Issue/PR URLs, exact commit SHA, acceptance criteria, test evidence and remaining risks. Do not assume conversations or uncommitted files are shared between tasks.
- Disclose AI assistance in public reviews. Models are not separate human contributors; never fabricate approvals or customer/production experience.
- Maximum two unresolved implementation/review rounds per packet, then return the evidence to design.
- No idle polling or recurring automation. Resume on a user request or a concrete handoff message.

## Scope and evidence

- The service is a personal learning MVP. Local tests, AWS mocks, GitHub CI, AWS operation and user-performed practice are different evidence categories.
- Repository publication does not authorize AWS deployment. Keep `AWS_DEPLOY_ENABLED=false` until separately authorized.
- Add useful improvements to Issues with priority and acceptance criteria. Progress on the current milestone; do not silently expand into unrelated services or paid infrastructure.
