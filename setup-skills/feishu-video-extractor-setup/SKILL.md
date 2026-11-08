---
name: feishu-video-extractor-setup
description: "Guide a new user through configuring the Feishu video/audio field shortcut and its backend from this repository. Use for first setup, migration to another computer/account, backend URL configuration, or first attachment verification."
---

# 飞书视频插件配置引导

Guide a new user through configuring the Feishu video/audio field shortcut and its backend from this repository. Use for first setup, migration to another computer/account, backend URL configuration, or first attachment verification.

## Locate and choose deployment

Read installed `references/installation.json` if present and verify `repository_path` has `onboarding.json`, `AGENTS.md`, `field-shortcut/` and `backend/`. Read `AGENTS.md`, `SETUP_OTHER_DEVICE.md` and the provider-specific guide before changes. Follow the current repository instructions; do not deploy the early sidebar when the user asked for the recommended field shortcut.

Reuse known inputs, then resolve only the missing OS, intended backend route (local test, macOS + Tunnel, or cloud/Docker host), user's own HTTPS origin and Feishu publishing permissions. `handoff/config.example.json` is a non-secret worksheet. Fill a local ignored copy such as `config.local.json`; never put secrets or login state in it. Local setup does not automatically authorize paid hosting, DNS changes, public deployment or store publication; execute those steps when within the user's explicit request and chosen account/provider.

## Prepare the selected route

1. Run `scripts/doctor.sh` or `.ps1`. Use the platform dependency installation script only for missing prerequisites. Never run Windows PowerShell instructions through a Unix shell or treat a cross-platform syntax check as Windows hardware validation.
2. For a local backend use `docker compose up --build` and check `/health`. Localhost cannot be fetched by Feishu's remote attachment service. For production select the user's reachable HTTPS origin; fill PUBLIC_BASE_URL, a newly generated TICKET_SECRET (32+ characters) and REQUIRE_BASE_SIGNATURE=true in their environment or secret store. Secrets must not be printed or pasted into this chat.
3. Configure `field-shortcut/src/config.ts` through `scripts/set-backend-url.sh` or `.ps1`. The public source deliberately uses a migration placeholder and should fail `npm run check-config` until configured. Do not reintroduce the maintainer's endpoint. In field-shortcut run `npm ci`, `npm run build`, `npm run pack`, then the root credential check. Keep generated ZIPs and environment files out of commits.
4. Guide publication through the user's Feishu account and select asynchronous execution. Before first publication the official shortcut ID may be unknown: leave EXPECTED_PACK_ID empty temporarily while keeping signature validation enabled. Fill the issued ID afterwards. A package build alone is not a published shortcut.
5. In the user's Base choose a text/URL source field, add the shortcut attachment field and select video or audio. Validate one authorized public link, HTTPS health, attachment retrieval and an intentional invalid link before batching.

## Diagnose only what failed

30 MB is the default output attachment limit; audio source input defaults to 500 MB. Try audio for large video output, explaining its speech-oriented low bitrate. For `Fresh cookies are needed`, configure only the user's own server-side cookie/browser-profile route; never collect or package Cookie files. A logged-in browser does not guarantee every source can be downloaded. The Mac must stay running for local service/Tunnel mode. Multiple backend replicas need shared prepared-file storage.

Report separately: dependencies ready, backend reachable, package built, shortcut published, first real attachment verified, and unresolved platform/login issues. Do not mark the full integration ready from a local health response alone.
