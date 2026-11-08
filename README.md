# 飞书多维表格视频 / 音频下载插件

将表格里的公开视频分享链接转成 **MP4 视频或 M4A 音频附件**，方便团队在多维表格中整理素材。

推荐使用 `field-shortcut/` 的**字段捷径**：选择一个存放链接的字段，结果写入捷径自己的附件字段。仓库还保留早期侧边栏实现，两者的安装方式和处理入口不同。

## 使用场景与组成

| 组件 | 做什么 | 谁需要配置 |
|---|---|---|
| 字段捷径 | 读取链接，触发解析，返回附件 | 飞书应用管理员 |
| FastAPI 后端 | 下载、转换音频、校验签名、提供临时附件 URL | 服务维护者 |
| 多维表格 | 填链接、选“音视频 / 仅音频”、查看结果 | 表格使用者 |
| macOS / Windows 助手 | 可选，本机浏览器登录态辅助下载 | 本机维护者 |

支持域名白名单包括抖音、TikTok、小红书、B 站、快手。各平台能否成功下载取决于视频访问条件、风控和解析器兼容性；不承诺所有链接都可用。

## 开始前需要什么

- 能创建或发布飞书字段捷径的账号与相应权限。
- 自己的公网 **HTTPS 后端地址**，飞书服务器需要能够访问临时附件链接。
- Node.js 20+、Python 3.10+；后端也可通过 Docker 运行。
- 自己的服务密钥和必要时的浏览器登录状态。仓库不提供现成公共下载服务或维护者的账号。

## 最短搭建路径

### 1. 下载源码并检查环境

```bash
git clone https://github.com/Guan-XX003/feishu-video-extractor.git
cd feishu-video-extractor
./scripts/doctor.sh
```

Windows 对应脚本见 `scripts/*.ps1`。完整迁移步骤见 [SETUP_OTHER_DEVICE.md](SETUP_OTHER_DEVICE.md)。

### 2. 先验证本地后端

```bash
docker compose up --build
# 另一个终端检查服务
curl http://localhost:8000/health
```

上述默认配置用于本地调试。正式部署前，在服务环境中设置：

```dotenv
PUBLIC_BASE_URL=https://your-backend.example.com
TICKET_SECRET=请替换为至少32字符的随机密钥
REQUIRE_BASE_SIGNATURE=true
EXPECTED_PACK_ID=你发布后获得的字段捷径ID
```

可用 `openssl rand -hex 32` 生成随机密钥。首次取得捷径 ID 前，`EXPECTED_PACK_ID` 可暂空，但签名校验必须开启；取得正式 ID 后补齐。不要把示例域名或示例密钥直接用于上线。

### 3. 配置自己的地址并打包字段捷径

```bash
./scripts/set-backend-url.sh https://your-backend.example.com
cd field-shortcut
npm ci
npm run build
npm run pack
```

把示例 URL 换成你的真实 HTTPS 后端域名。公开源码中的 `BACKEND_URL` 是待配置占位符，未设置时构建检查会阻止打包。

### 4. 在自己的飞书账号发布

1. 在飞书的字段捷径开发 / 发布入口创建自己的应用，设置所需权限。
2. 上传 `field-shortcut/output/output_*.zip`，按发布入口要求完成配置。
3. 选择**异步执行模式**；后端需要先预下载，再提供临时下载链接。
4. 把正式捷径 ID 填到后端 `EXPECTED_PACK_ID`，保持签名校验开启。
5. 在多维表格添加这个捷径字段，选择链接来源字段与下载模式，先测试一条可访问的公开视频。

更详细的调试和发布步骤见 [字段捷径指南](field-shortcut/README.md)。

## 表格使用者怎么用

在文本或 URL 字段填入分享链接 → 在新增的捷径字段中选择这个来源字段 → 选择“音视频”或“仅音频” → 运行捷径并等待附件生成。

视频超过附件限制时，可尝试“仅音频”。字段捷径结果回到自己的附件字段；早期侧边栏则可以另选目标附件字段并选择当前记录、视图或全表未处理记录。

## 限制和常见错误

| 情况 | 说明或处理 |
|---|---|
| 附件超过 30 MB | 后端默认拒绝过大输出，尝试仅音频 |
| `Fresh cookies are needed` | 使用自己的授权浏览器状态或更新服务端 Cookie；平台仍可能拒绝个别视频 |
| `1254403 / 800004783` | 核对签名、应用授权和允许的捷径 ID |
| `1254406 / 800004789` | 检查链接、后端日志及下载限制 |
| 慢速隧道下载失败 | 确认附件可及时从公网获取；可改为仅音频或更稳定的主机 |

仅音频采用低码率 AAC，更适合口播，不能代替高保真音乐下载。源媒体默认限制 500 MB，音频附件仍限制 30 MB。缓存文件通过短期票据提供，多副本后端须使用共享存储或自行改造对象存储。

## 可选运行方式与开发入口

- [macOS 常驻服务与 Tunnel](mac-server/README.md)：需要本机持续运行；登录状态可能失效，仍需维护。
- [Windows 本地下载助手](windows-worker/README.md)：可选本机下载 Worker。
- [完整部署说明](docs/DEPLOYMENT_GUIDE.md)：后端与早期侧边栏的详细配置。
- [Agent 接管说明](docs/AGENT_START_HERE.md)与 [配置工作表](handoff/config.example.json)。

提交或打包前运行 `./scripts/verify-no-secrets.sh`。后端测试与字段构建命令见 [AGENTS.md](AGENTS.md)。

只处理你有权保存的内容；Cookie、`.env`、Token 和浏览器目录仅保存在你控制的环境中。生产后端应开启鉴权和限流，不要直接作为匿名公共下载接口。

[反馈问题](https://github.com/Guan-XX003/feishu-video-extractor/issues)请提供系统、运行方式、错误码和脱敏日志，不要提交登录凭据。
