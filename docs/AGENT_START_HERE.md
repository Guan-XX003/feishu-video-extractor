# Agent 接管入口

这份文档的目标是：把源码包或 GitHub 仓库交给一台新电脑上的 Agent 后，即使它没有本会话上下文，也能安全地从零配置并发布。

## 给 Agent 的第一条指令

可以把下面这段原样发给新电脑上的 Agent：

> 请接管这个飞书多维表格字段捷径项目。先完整阅读根目录 `AGENTS.md`、`docs/AGENT_START_HERE.md`、`SETUP_OTHER_DEVICE.md` 和 `handoff/config.example.json`。先运行环境检查和敏感信息检查，不要复用或索取旧电脑的 Cookie、Railway Token、TICKET_SECRET、WORKER_TOKEN。使用我的新飞书账号和新后端环境完成部署、打包和测试。遇到登录、验证码或需要我授权的页面时停下来让我操作。完成后交付后端 URL、正式 shortcut_id、Railway 变量清单、字段捷径 ZIP 路径和三项测试结果。

## Agent 首次执行顺序

macOS/Linux：

```bash
./scripts/doctor.sh
./scripts/verify-no-secrets.sh
./scripts/install-dependencies.sh
```

Windows PowerShell：

```powershell
.\scripts\doctor.ps1
.\scripts\verify-no-secrets.ps1
.\scripts\install-dependencies.ps1
```

如果检查脚本报告缺少软件，先安装缺少项，再重新运行检查。不要在未检查敏感信息的目录中直接创建公开仓库或上传压缩包。

## 人必须提供或亲自完成的内容

Agent 可以写代码、部署、设置普通变量和验证服务，但以下内容应由目标用户提供或在登录界面亲自完成：

- 目标飞书账号登录和企业管理员审批；
- Railway/GitHub 登录；
- 抖音登录、验证码和 Cookie 导出授权；
- 新插件的显示名称、图标和发布范围；
- 是否启用 Windows 本地下载助手；
- 是否允许公开发布。默认应保持公司内部或私有。

## 新环境必须重新生成的值

| 项目 | 能否从旧电脑复制 | 说明 |
|---|---:|---|
| 源代码 | 可以 | 使用无密钥迁移包或私有 GitHub 仓库 |
| `BACKEND_URL` | 不建议 | 应指向新环境自己的 HTTPS 后端 |
| `shortcut_id` | 不可以 | 每个新发布的字段捷径会产生自己的 ID |
| `TICKET_SECRET` | 不可以 | 每个部署重新随机生成，至少 32 字符 |
| `WORKER_TOKEN` | 不可以 | 启用 Windows Worker 时重新生成 |
| 抖音 Cookie | 不可以 | 必须由目标用户的浏览器重新导出 |
| Railway/GitHub Token | 不可以 | 在目标电脑重新登录 CLI |

## 最小可用路径

1. 填写 `handoff/config.example.json` 的非敏感字段，另存为本地文件；不要提交含账号信息的副本。
2. 部署 `backend/` 到 Railway，设置 `backend/railway.env.example` 中的生产变量。
3. 访问 `https://后端域名/health`。
4. 用 `scripts/set-backend-url.*` 写入字段捷径后端地址。
5. 在 `field-shortcut/` 执行 `npm run build && npm run pack`。
6. 在飞书发布字段捷径，选择异步执行模式。
7. 将正式 `shortcut_id` 加到 Railway 的 `EXPECTED_PACK_ID`。
8. 导出目标用户自己的抖音 Cookie，写入 Railway `COOKIES_CONTENT`。
9. 等待部署后测试音频、视频和错误提示。

## 完成交付标准

Agent 最终应提供：

- 后端生产 URL 与 `/health` 检查结果；
- Railway 项目/服务名称（不输出任何 secret 值）；
- 正式字段捷径名称、版本、`shortcut_id` 和发布范围；
- 最新字段捷径 ZIP 的本地路径；
- 音频测试、视频测试、无效链接测试结果；
- Cookie 更新方法和下一次失效时的处理步骤；
- 所有源码变更的 Git commit。
