# 视频链接提取字段捷径

## 发布资料

- 显示名称：`视频下载（Growing）`
- 图标：`assets/changqing-video-downloader-icon-512.png`
- 简介：`将抖音、小红书、B 站、快手和 TikTok 分享链接自动转为视频或音频附件。`

显示名称和图标需在飞书字段捷径的发布资料页中设置，不会从 ZIP 包自动更新。

这是飞书多维表格 FaaS 版“字段捷径”，最终字段类型为附件。

用户添加捷径字段时，选择存放分享链接的文本或 URL 字段，并选择“音视频”或“仅音频”。飞书会自动调用捷径，把解析后的媒体写进当前记录的附件字段。

## 本地调试

1. 启动项目根目录的后端服务。
2. 确认 `src/config.ts` 中的地址为 `http://127.0.0.1:8000`。
3. 安装依赖并启动字段服务：

```bash
npm install
npm run start
```

4. 在飞书多维表格中安装“字段捷径调试助手”，连接本地服务并创建调试字段。

## 正式打包

1. 将后端部署到公网 HTTPS。
2. 把 `src/config.ts` 的 `BACKEND_URL` 改为部署地址。
3. 后端设置：

```env
PUBLIC_BASE_URL=https://你的后端域名
TICKET_SECRET=足够长的随机字符串
REQUIRE_BASE_SIGNATURE=true
EXPECTED_PACK_ID=发布后获得的字段捷径ID
```

首次提交前还没有字段捷径 ID 时，`EXPECTED_PACK_ID` 可以暂时留空，但必须启用
`REQUIRE_BASE_SIGNATURE=true`。获得正式 ID 后再补充该值并重新部署后端。

同一个后端如果服务多个飞书账号或多个字段捷径，可将 ID 用英文逗号分隔，例如：

```env
EXPECTED_PACK_ID=pack_id_a,pack_id_b,pack_id_c
```

后端仍会验证飞书签名；这里只是登记多个允许调用的字段捷径 ID，并不会关闭鉴权。

4. 构建并打包：

```bash
npm run build
npm run pack
```

上传 `output/output_*.zip` 到字段捷径发布入口。

发布时请选择异步执行模式。后端会在 `execute` 阶段先完成视频解析和下载，再返回带 `Content-Length` 的临时附件地址；飞书要求单个附件不超过 30 MB，且附件 URL 的 GET 下载需在 1 分钟内完成。

“仅音频”模式会使用项目依赖自带的 FFmpeg 运行时转换为 M4A，无需单独安装系统 FFmpeg。音频附件仍受 30 MB 上限约束，源媒体默认最多允许 500 MB，可通过 `MAX_AUDIO_SOURCE_SIZE_MB` 调整。

如果后端运行多个副本，请为 `PREPARED_VIDEO_DIR` 配置共享持久卷，或将临时文件缓存替换为对象存储。

抖音当前可能要求新鲜 Cookie。后端支持通过 `COOKIES_FILE` 指向 Netscape 格式的 `cookies.txt`；文件应只包含 `douyin.com` 和 `iesdouyin.com`，并作为服务器密钥管理，不能打进字段捷径包。

仅用于用户有权下载的公开、无登录、无 DRM 视频。
