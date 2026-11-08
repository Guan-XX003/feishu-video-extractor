# Windows Local Download Worker

The worker keeps Douyin browser state on the Windows machine. It opens no inbound port: it long-polls the Railway backend, downloads a claimed job with the selected local browser profile, and uploads only the finished MP4/M4A result.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- Chrome, Edge, or Firefox
- The worker must run as the same Windows user that owns the browser profile

## Install

Run PowerShell as the target user from this directory:

```powershell
.\install.ps1 `
  -BackendUrl "https://your-service.up.railway.app" `
  -WorkerToken "<same secret as Railway WORKER_TOKEN>" `
  -Browser edge
```

Replace `your-service.up.railway.app` with your own reachable backend hostname before running the command.

The installer creates `%LOCALAPPDATA%\FeishuVideoWorker` and a logon scheduled task named `Feishu Video Download Worker`. The token is stored in a user-only ACL-protected config file.

For Edge, the installer also creates `Douyin Worker Login.lnk` on the desktop. Open that shortcut, log in to Douyin, and then close the dedicated Edge window. The worker reads this isolated profile, so the user's normal Edge windows do not lock the Cookie database.

The task intentionally runs only while that Windows user is logged in, because browser cookies are encrypted for the user profile.
