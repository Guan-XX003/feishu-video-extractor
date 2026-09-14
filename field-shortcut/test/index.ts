import assert from 'node:assert/strict';
import { FieldCode } from '@lark-opdev/block-basekit-server-api';
import basekit, { extractFirstUrl, normalizeMediaType } from '../src';

assert.equal(
  extractFirstUrl([{ type: 'text', text: '复制打开 https://v.douyin.com/demo/ 查看视频' }]),
  'https://v.douyin.com/demo/',
);
assert.equal(
  extractFirstUrl({ link: 'https://www.bilibili.com/video/BV1demo', title: '视频' }),
  'https://www.bilibili.com/video/BV1demo',
);
assert.equal(
  extractFirstUrl(
    '2.51 :0pm 04/02 Eho:/ [X@M.jp](http://X@M.jp) 团队操盘手述职现场 '
      + '[https://v.douyin.com/PxbvFF5DYTw/](https://v.douyin.com/PxbvFF5DYTw/)',
  ),
  'https://v.douyin.com/PxbvFF5DYTw/',
);
assert.equal(
  extractFirstUrl(
    'https://user@n.wf/tracking https://v.douyin.com/DNiHht4F72A/ 复制链接打开抖音',
  ),
  'https://v.douyin.com/DNiHht4F72A/',
);
assert.equal(extractFirstUrl('https://user@n.wf/tracking'), null);
assert.equal(normalizeMediaType('audio'), 'audio');
assert.equal(normalizeMediaType('仅音频'), 'audio');
assert.equal(normalizeMediaType({ value: 'audio', label: '仅音频' }), 'audio');
assert.equal(normalizeMediaType([{ value: 'audio' }]), 'audio');
assert.equal(normalizeMediaType('video'), 'video');

const field = basekit.field;
assert.ok(field, '字段捷径未注册');

async function run() {
  let requestBody: Record<string, unknown> | undefined;
  const success = await field.execute(
    {
      source: [{ type: 'url', link: 'https://v.douyin.com/demo/' }],
      mediaType: 'audio',
    },
    {
      baseSignature: 'local-debug-signature',
      baseID: 'base-demo',
      tableID: 'table-demo',
      packID: 'pack-demo',
      tenantKey: 'tenant-demo',
      logID: 'log-demo',
      token: '',
      timeZone: 'Asia/Shanghai',
      baseOwnerID: 'owner-demo',
      isNeedPayPack: false,
      hasQuota: true,
      fetch: async (_url, options) => {
        requestBody = JSON.parse(String(options?.body));
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({
            download_url: 'https://video.example.com/api/download/ticket',
            filename: 'audio-demo.m4a',
            expires_in: 600,
          }),
        } as any;
      },
    },
  );

  assert.deepEqual(success, {
    code: FieldCode.Success,
    data: [
      {
        name: 'audio-demo.m4a',
        content: 'https://video.example.com/api/download/ticket',
        contentType: 'attachment/url',
      },
    ],
  });
  assert.equal(requestBody?.media_type, 'audio');
  assert.equal(requestBody?.log_id, 'log-demo');

  const mediaModeItem = field.formItems.find((item) => item.key === 'mediaType');
  assert.equal(mediaModeItem?.defaultValue, 'video');

  console.log('field shortcut tests passed');
}

void run();
