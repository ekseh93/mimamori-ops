# Contributing

Mimamori Ops is an AI-assisted individual learning project. The maintainer is `@ekseh93`. AI design and review support is labeled explicitly; it is not represented as independent human approval or commercial experience.

## One change through the pipeline

1. Open an Issue with a concrete problem and acceptance criteria. Use the bug, feature or incident form.
2. Fetch `origin/main` and create `codex/<issue-number>-<short-purpose>` in a clean worktree.
3. Commit a small coherent change, run focused checks, and push the branch. Create a draft PR linked with `Closes #<issue-number>`.
4. Record test commands and actual results in the PR. Distinguish mock tests, GitHub CI and real AWS observations.
5. Ask the Sol review task to inspect the exact implementation HEAD. Post its findings as an **AI-assisted review** comment, never as fabricated human approval.
6. Resolve findings, pass required checks, and mark the PR ready. Squash-merge using the current repository rules. Confirm main's CI and the linked Issue status.

While only one human maintainer exists, approving review count is zero. PRs and automated checks are still required. When a second human joins, increase it to one and enable the appropriate code-owner review requirement. A CODEOWNERS entry is ownership routing, not proof that review happened.

## Commit messages

- `feat: add ...` for behavior
- `fix: correct ...` for a defect
- `test: cover ...` for meaningful regression coverage
- `docs: explain ...` for documentation
- `ci: validate ...` for automation
- `security: restrict ...` for access or publication safeguards

Commit and push at these milestones, not after every line. Keep incomplete exploratory changes local until they form a useful review unit. Do not rewrite or force-push shared history without an explicit reason and authorization.

## Local checks

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m unittest discover -s tests -v
python scripts/check_public_content.py
```

For packaging and Terraform changes follow `docs/03-runbook.ko.md`. Do not run Terraform apply as part of routine CI. Use only an owned or explicitly authorized target for live network checks.

## Security and dependencies

- Report possible secrets or exploitable vulnerabilities through GitHub's private vulnerability reporting, not a public Issue.
- Never commit Terraform state/plan/variables, local registry, API keys or customer-specific data.
- Dependabot updates require normal CI and review. Keep boto3/botocore-related version changes together.
- Dependency Review rejects newly introduced high/critical known vulnerabilities; CodeQL provides separate static analysis. Neither guarantees absence of vulnerabilities.

## Learning and public communication

Public documentation is primarily Japanese/English; the learner guide is Korean. Japanese interview practice includes Korean translation. Describe only the work actually performed, its observations and limitations. For the UI tour, see `docs/08-github-collaboration.ko.md`.
