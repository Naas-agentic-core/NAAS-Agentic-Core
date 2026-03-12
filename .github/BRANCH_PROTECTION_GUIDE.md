# Branch Protection Guide (Authoritative)

This repository uses a **single mergeability truth**: `required-ci`.

## Required settings for `main`

- Require pull request before merging: **enabled**
- Require approvals: **1+** (increase to 2 when team grows)
- Dismiss stale approvals when new commits are pushed: **enabled**
- Require review from Code Owners: **enabled**
- Require status checks to pass before merging: **enabled**
- Require branches to be up to date before merging: **enabled**
- Restrict who can push directly to matching branches: **enabled**
- Do not allow bypassing the above settings: **enabled**
- Allow force pushes: **disabled**
- Allow deletions: **disabled**

## Required status checks

Exactly one required check:
- `required-ci`

`required-ci` already aggregates `lint`, `contracts`, `guardrails`, and `test`.
Do **not** require both aggregate and underlying jobs in branch protection.

## Why this model

- Prevents duplicated failure surfaces (`build` + `verify` + `required-ci`).
- Keeps PR failure reason obvious in one workflow.
- Reduces configuration drift between docs and GitHub settings.

## Change control

Any change to required checks must update, in one PR:
1. `.github/workflows/ci.yml`
2. `.github/BRANCH_PROTECTION_GUIDE.md`
3. `CONTRIBUTING.md`
