# Agent operating guide

Read this file before changing, deploying, packaging, or publishing the project.

## Objective

This repository implements a Feishu/Lark Base field shortcut that converts supported public video links into MP4 or M4A attachments. It consists of:

- `field-shortcut/`: Feishu field-shortcut server package.
- `backend/`: FastAPI download, signature-validation, temporary-ticket, and file-serving backend.
- `windows-worker/`: optional Windows downloader that uses a local browser profile.
- `src/`: legacy sidebar frontend; do not confuse it with the recommended field shortcut.

Start migration work from `docs/AGENT_START_HERE.md` and use `handoff/config.example.json` as the non-secret configuration worksheet.

## Security rules

Never commit, upload, print, or put into a field-shortcut ZIP any of the following:

- `.env` files containing real values;
- `backend/cookies*.txt` or browser cookies;
- Railway/GitHub/Feishu access tokens;
- `TICKET_SECRET` or `WORKER_TOKEN`;
- browser profile directories or exported session data.

Cookie data belongs only in the target backend's secret store (`COOKIES_CONTENT`) or on the optional Windows worker. Each deployment must use newly generated secrets and the target user's own browser login.

Before committing or packaging, run:

```bash
./scripts/verify-no-secrets.sh
```

## Required migration sequence

1. Run `./scripts/doctor.sh` (or `scripts/doctor.ps1` on Windows).
2. Install dependencies with the platform script in `scripts/`.
3. Create a new backend deployment and new secrets. Do not reuse the source machine's Railway project or secrets unless the user explicitly requests that exact shared deployment.
4. Set `PUBLIC_BASE_URL`, `TICKET_SECRET`, and `REQUIRE_BASE_SIGNATURE=true`.
5. Initially leave `EXPECTED_PACK_ID` empty only while obtaining the first official shortcut ID. Keep signature verification enabled.
6. Set the backend URL with `./scripts/set-backend-url.sh https://...` or the PowerShell equivalent.
7. Build and pack `field-shortcut/`.
8. The user must publish/upload through the target Feishu account. Use asynchronous execution mode.
9. Add the official `shortcut_id` to `EXPECTED_PACK_ID`. Multiple IDs are comma-separated.
10. Export fresh Douyin cookies from the target user's browser and store them in backend secrets, or enable the Windows worker.
11. Verify `/health`, one audio job, one video job under 30 MB, and an intentional invalid-link error.

## Canonical commands

```bash
./scripts/doctor.sh
./scripts/install-dependencies.sh
PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests
(cd field-shortcut && npm run build && npm run pack)
./scripts/verify-no-secrets.sh
./package-source.sh
```

Windows equivalents are provided as `.ps1` files where relevant.

## Backend configuration invariants

- Production must use HTTPS.
- `REQUIRE_BASE_SIGNATURE=true` in production.
- `TICKET_SECRET` and enabled `WORKER_TOKEN` must be at least 32 characters.
- `EXPECTED_PACK_ID` accepts one ID or a comma-separated allowlist.
- Attachment output is limited to 30 MB by default.
- Cookies must contain only Douyin-related domains and must never be version controlled.
- A single Railway instance uses ephemeral local cache. Do not run multiple replicas unless `PREPARED_VIDEO_DIR` is shared or replaced with object storage.

## Validation and error mapping

- `1254403 / 800004783`: authorization/signature/allowed shortcut ID failure.
- `1254406 / 800004789`: invalid input or downloader returned HTTP 400/422; inspect Railway logs by `log_id`.
- `1254500`: general backend or field-shortcut failure.
- `Fresh cookies are needed`: refresh `COOKIES_CONTENT` or use the Windows worker.
- Video over 30 MB: select audio or use a smaller source.

## Change discipline

- Preserve the target account's own names, IDs, domains, and credentials.
- Do not hardcode a user's backend URL except in `field-shortcut/src/config.ts` for that specific build.
- Update documentation and templates when adding an environment variable.
- Run backend tests and the field-shortcut build before release.
- The pinned Feishu CLI dependency tree currently reports legacy npm audit/deprecation warnings. Do not run `npm audit fix --force` or upgrade `@lark-opdev/*` blindly; first verify compatibility with the current Feishu field-shortcut runtime and rebuild the package.
- Do not publish publicly or change repository visibility without explicit user authorization.
