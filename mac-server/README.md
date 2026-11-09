# macOS local server

This mode replaces Railway and the Windows worker with one always-on Mac:

```text
Feishu field shortcut -> Cloudflare Tunnel -> 127.0.0.1:8000 -> yt-dlp/FFmpeg
                                                        -> dedicated Edge/Chrome profile
```

The browser profile and generated secrets stay under:

```text
~/Library/Application Support/FeishuVideoExtractor/
```

They are never copied into the repository.

## Install the local backend

```bash
./mac-server/install.sh --origin https://YOUR_TENANT.feishu.cn
./mac-server/status.sh
```

Replace `YOUR_TENANT` with your own Feishu tenant name. The installer refuses to run with its default placeholder origin; pass `--origin` for your account.

The installer creates a user LaunchAgent named
`com.growing.feishu-video-extractor`. It binds only to `127.0.0.1:8000`,
generates a fresh ticket secret, enables Feishu signature validation, and
allows the existing production shortcut ID by default. While connected to AC
power, the LaunchAgent uses macOS `caffeinate -s` to prevent idle system sleep;
the display may still turn off and the screen may still be locked.

## Log in to Douyin

Open:

```bash
open "$HOME/Library/Application Support/FeishuVideoExtractor/open-douyin-login.command"
```

Log in inside this dedicated browser window. You can leave it open or close it;
the backend starts the dedicated browser invisibly in headless mode when needed.
It uses a debugging port bound only to `127.0.0.1` to load a blocked Douyin page
in the background and refresh the dynamic anti-bot cookies. Normal downloads do
not open browser windows or tabs. The backend reads cookies from this profile at
download time, so there is no Railway cookie environment variable to refresh.

## Add a stable public URL

Use a named Cloudflare Tunnel and a hostname on a domain managed by the same
Cloudflare account. Point the hostname to `http://127.0.0.1:8000`. Do not use a
Quick Tunnel for production because its hostname changes.

After the tunnel hostname is ready:

```bash
./mac-server/install-cloudflare-tunnel.sh
./mac-server/set-public-url.sh https://video-api.example.com
./scripts/set-backend-url.sh https://video-api.example.com
```

Then rebuild and publish one new field-shortcut version. Future backend moves
can keep the same hostname and will not require another shortcut release.

The tunnel installer also runs a silent health check every two minutes. When
the local backend is healthy but the tunnel is disconnected or its public
health URL is unavailable, it restarts only the `com.growing.feishu-video-tunnel`
LaunchAgent. Restarts are limited to once every five minutes. Diagnostic logs
are stored in `~/Library/Application Support/FeishuVideoExtractor/logs/`.

## Availability requirements

- Keep the Mac connected to power and prevent idle system sleep.
- The macOS user must remain logged in so Chromium cookies can be decrypted
  through that user's Keychain. Locking the screen is fine.
- Restart and log in after macOS updates before expecting downloads to work.
- Only expose the HTTP backend through Tunnel; do not expose SSH or Screen
  Sharing through this hostname.

The shortcut allowlist starts empty for first-time setup. After publishing your own shortcut, pass its official ID using `--pack-id YOUR_SHORTCUT_ID`.
