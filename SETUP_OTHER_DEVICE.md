# 在其他电脑和其他飞书账号搭建

这份项目是“源码模板”，不是绑定当前账号的安装程序。迁移到另一台电脑、另一个飞书账号时，需要重新创建飞书字段捷径应用，并重新配置后端密钥与抖音登录态。

## 需要准备

- macOS、Linux 或 Windows 电脑
- Node.js 20+（字段捷径打包）
- Python 3.10+（本地测试；Windows 下载助手建议 Python 3.11+）
- 一个有权限创建/发布字段捷径的飞书账号
- 一个 Railway 账号，或其他可运行 Docker/FastAPI 的公网 HTTPS 主机
- 该环境自己的抖音登录账号

## 第一步：复制源码

解压源码包后进入项目目录。不要把以下内容从旧电脑复制过去：

- `.env` 文件
- `backend/cookies*.txt`
- Railway CLI 配置目录
- 任何包含 `TOKEN`、`SECRET`、Cookie 的文件

## 第二步：部署后端

### Railway CLI 方式

```bash
cd feishu-video-extractor
railway login
railway init
railway link                 # 选择刚创建的项目和 production 环境
railway up --service feishu-video-extractor
```

在 Railway Variables 中设置：

```env
ALLOWED_ORIGINS=https://你的飞书域名
PUBLIC_BASE_URL=https://你的后端域名
TICKET_SECRET=随机生成的至少32字符密钥
REQUIRE_BASE_SIGNATURE=true
EXPECTED_PACK_ID=发布后得到的字段捷径ID
```

如果多个字段捷径共用一个后端，把 ID 用英文逗号分隔：

```env
EXPECTED_PACK_ID=pack_id_a,pack_id_b
```

部署后访问 `https://你的后端域名/health`，确认返回 `"ok": true`。

### Docker 方式

```bash
docker compose up --build -d
```

生产环境必须把示例值替换为自己的密钥，并使用 HTTPS 反向代理。不要直接把后端开放成无鉴权公共下载接口。

## 第三步：配置抖音 Cookie

1. 在当前电脑的 Chrome 或 Edge 登录自己的抖音账号。
2. 运行：

```bash
cd backend
./export_douyin_cookies.sh chrome   # Edge 改为 edge
```

3. 将生成的 `cookies.douyin.txt` 内容作为 Railway 的 `COOKIES_CONTENT` 变量保存。

Cookie 只应保存在后端密钥环境变量中，不能提交到 Git、不能放进字段捷径 ZIP，也不能发给其他使用者。

## 第四步：创建并发布新字段捷径

1. 在新飞书账号的开放平台创建字段捷径应用。
2. 将 `field-shortcut/src/config.ts` 中的 `BACKEND_URL` 改成新的后端 HTTPS 地址。
3. 构建并打包：

```bash
cd field-shortcut
npm install
npm run build
npm run pack
```

4. 将 `output/output_*.zip` 上传到该飞书账号的字段捷径发布入口。
5. 发布后记下新的正式 `shortcut_id`，填入 Railway 的 `EXPECTED_PACK_ID`，保存并等待重新部署。
6. 在多维表格添加字段捷径字段，选择链接字段和“音视频/仅音频”，用一条公开视频测试。

## 可选：Windows 本地下载助手

如果 Railway 服务器经常被抖音风控，使用 Windows 助手会更稳定：

```powershell
.\install.ps1 `
  -BackendUrl "https://你的后端域名" `
  -WorkerToken "Railway 中自己的 WORKER_TOKEN" `
  -Browser edge
```

然后打开桌面的 `Douyin Worker Login.lnk`，在专用 Edge 窗口登录抖音。下载助手必须以拥有该浏览器登录态的 Windows 用户运行。

同时在 Railway 设置：

```env
WORKER_ENABLED=true
WORKER_TOKEN=随机生成的至少32字符密钥
```

## 常见错误

- `1254403 / 800004783`：字段捷径 ID 不在后端 `EXPECTED_PACK_ID` 允许列表中。
- `1254406 / 800004789`：参数或下载失败；如果日志出现 `Fresh cookies`，更新后端 Cookie。
- `1254500`：后端内部错误，查看 Railway logs。
- 视频超过 30 MB：选择“仅音频”，或降低源视频大小。

## 安全边界

只下载自己有权处理的公开内容。该项目不用于绕过登录、付费墙、DRM 或访问控制。每个飞书账号都应使用自己的应用、自己的 Cookie 和自己的密钥。
