# 飞书视频链接提取字段捷径

项目现在包含正式的飞书多维表格 FaaS“字段捷径”版本，以及早期的侧边栏版本。字段捷径会读取用户选择的分享链接字段，并把视频直接生成在捷径附件字段中。

## 字段捷径（推荐）

字段捷径代码位于 `field-shortcut/`：

- 添加字段时选择“视频链接提取”捷径
- 在配置面板选择存放分享链接的文本或 URL 字段
- 选择下载“音视频”或“仅音频”，大视频可改为提取 M4A 音频
- 捷径自动运行，结果直接显示为当前字段中的视频附件
- 不需要用户再打开侧边栏逐条点击

本地测试、打包和发布方法见 `field-shortcut/README.md`。

## 功能

- 选择“分享链接”来源字段和“视频附件”目标字段
- 支持当前记录、当前视图、全表未处理记录三种范围
- 已有附件的记录自动跳过
- 逐条显示成功、跳过、失败日志
- 后端域名白名单、并发限制、30 MB 文件大小限制
- 默认解析公开、无登录、无 DRM 的视频

默认白名单包含抖音、TikTok、小红书、Bilibili、快手。平台页面结构变化时，可能需要升级 `yt-dlp` 或接入其他解析服务。

## 目录

```text
src/       飞书侧边栏前端（React + Vite + Base JS SDK）
backend/   视频解析下载服务（FastAPI + yt-dlp）
field-shortcut/ 飞书 FaaS 字段捷径
```

## 本地启动

### 1. 启动后端

```bash
docker compose up --build
```

健康检查：`http://localhost:8000/health`

### 2. 启动前端

```bash
npm install
cp .env.example .env
npm run dev
```

本地独立预览时，可在 `.env` 中设置：

```env
VITE_DEMO_MODE=true
```

## 接入飞书

### 字段捷径

1. 部署后端到公网 HTTPS。
2. 将 `field-shortcut/src/config.ts` 中的后端地址替换为部署地址。
3. 在 `field-shortcut/` 运行 `npm run pack`。
4. 将 `field-shortcut/output/output_*.zip` 上传到飞书字段捷径发布入口。
5. 在多维表格中新建字段，选择该捷径并指定分享链接字段。
6. 发布时选择异步执行模式，让视频预下载可使用最长 15 分钟的执行时间。

后端会先把视频准备到临时缓存，再把带 `Content-Length` 的短期下载链接返回给飞书。单机部署可直接使用本地缓存；多副本部署时应把 `PREPARED_VIDEO_DIR` 放到共享持久卷，或改为对象存储。

抖音可能要求新鲜 Cookie。此时将只包含 `douyin.com` 和 `iesdouyin.com` 的 Netscape `cookies.txt` 放到后端服务器，并设置 `COOKIES_FILE`。不要提交 Cookie 文件到代码仓库，也不要把它传给字段捷径前端。

本地 Chrome 登录后可运行 `backend/export_douyin_cookies.sh chrome`，脚本只保留抖音域名 Cookie，并生成 `backend/cookies.douyin.txt`。使用 Edge 时把参数改为 `edge`。

## 在其他电脑、其他飞书账号上搭建

本项目可以迁移到任意一台 macOS、Linux 或 Windows 开发机，但不会自动迁移当前飞书账号、Railway 登录态或抖音登录态。每个新账号/新环境都应重新完成以下配置：

1. 复制本项目源码，不要复制 `.env`、`backend/cookies*.txt`、Railway 配置文件或任何 Token。
2. 在该飞书账号的开放平台创建自己的字段捷径应用，按飞书开发指南配置权限并取得应用/字段捷径 ID。
3. 部署一个自己的后端（Railway、Render、Docker 主机均可），设置新的 `TICKET_SECRET`，并开启 `REQUIRE_BASE_SIGNATURE=true`。
4. 将该账号发布后得到的字段捷径 ID 写入 `EXPECTED_PACK_ID`。多个字段捷径共用一个后端时，用英文逗号分隔，例如 `id_a,id_b`。
5. 在新电脑登录自己的抖音账号，运行 `backend/export_douyin_cookies.sh chrome` 或 `edge`，再将生成的 Cookie 作为服务器端 `COOKIES_CONTENT` 更新到后端；不要把 Cookie 放进字段捷径 ZIP。
6. 将 `field-shortcut/src/config.ts` 中的 `BACKEND_URL` 改为新的后端 HTTPS 地址，执行 `npm install && npm run build && npm run pack`，把生成的 ZIP 上传到该飞书账号的字段捷径发布入口。
7. 在多维表格中添加字段捷径，选择链接字段和“音视频/仅音频”，先用一条公开视频验证，再批量使用。

如果使用 Windows 本地下载助手，可按 `windows-worker/README.md` 安装。它必须以拥有浏览器登录态的 Windows 用户运行；Railway 只保存任务，不保存该浏览器的 Cookie。

### 打包可迁移源码

在项目父目录执行：

```bash
tar --exclude='node_modules' --exclude='backend/.venv' --exclude='backend/cookies*.txt' \
  --exclude='*.env' --exclude='field-shortcut/output' \
  -czf feishu-video-extractor-source.tar.gz feishu-video-extractor
```

解压后按上面的步骤重新配置即可。源码包不包含当前环境的 Cookie、Token、Railway 登录信息或已发布 ZIP。

### 侧边栏旧版本

1. 在飞书多维表格中创建侧边栏扩展。
2. 将构建后的前端部署到 HTTPS 静态站点。
3. 把部署地址填入扩展页面地址。
4. 设置 `VITE_API_BASE_URL` 为已部署的 HTTPS 后端地址并重新构建。
5. 后端 `ALLOWED_ORIGINS` 填写前端的完整 HTTPS Origin。

构建前端：

```bash
npm run build
```

## 字段约定

- 来源字段：文本、URL 或手机号类型（手机号类型仅为兼容 SDK 文本读取，实际应选择文本/URL）
- 目标字段：附件类型
- 若缺少字段，插件可创建“分享链接”和“视频附件”两个默认字段

## 安全与合规

- 只处理用户有权下载的公开视频。
- 不提供登录态、Cookie、付费墙、DRM 或访问控制绕过能力。
- 不建议开放为无鉴权公共服务；生产部署应在网关增加登录、限流和审计。
- 视频文件会在响应结束后从后端临时目录删除。

## 已知限制

- 字段捷径附件单文件上限为 30 MB，后端默认按该限制拒绝更大的视频。
- 仅音频模式会下载源媒体并用 FFmpeg 提取 M4A，源媒体默认限制为 500 MB。
- 部分平台链接可能因风控、地区限制或页面变化而解析失败。
- 当前 MVP 串行处理记录，避免对平台和飞书附件上传造成突发压力。
