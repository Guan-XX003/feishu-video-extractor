import {
  basekit,
  FieldCode,
  FieldComponent,
  FieldType,
  type FieldContext,
} from '@lark-opdev/block-basekit-server-api';
import { BACKEND_URL } from './config';

type TextSegment = {
  type?: string;
  text?: string;
  link?: string;
};

type UrlFieldValue = {
  link?: string;
  title?: string;
};

type TicketResponse = {
  download_url: string;
  filename: string;
  expires_in: number;
};

type MediaType = 'video' | 'audio';

const supportedVideoDomains = [
  'douyin.com',
  'iesdouyin.com',
  'tiktok.com',
  'xiaohongshu.com',
  'xhslink.com',
  'bilibili.com',
  'b23.tv',
  'kuaishou.com',
];

class BackendRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const backendHost = new URL(BACKEND_URL).hostname;
basekit.addDomainList([backendHost]);

function extractUrls(value: unknown): string[] {
  if (typeof value === 'string') {
    return value.match(/https?:\/\/[^\s()[\]<>（）、，。；;！!]+/giu) ?? [];
  }

  if (Array.isArray(value)) {
    return value.flatMap((item) => extractUrls(item));
  }

  if (value && typeof value === 'object') {
    const urlValue = value as UrlFieldValue;
    return [urlValue.link, (value as TextSegment).text, urlValue.title]
      .flatMap((item) => extractUrls(item))
      .filter((item, index, items) => items.indexOf(item) === index);
  }

  return [];
}

function isSupportedVideoUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase().replace(/\.$/, '');
    return (
      !url.username &&
      !url.password &&
      supportedVideoDomains.some(
        (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
      )
    );
  } catch {
    return false;
  }
}

export function extractFirstUrl(value: unknown): string | null {
  const urls = extractUrls(value);
  return urls.find(isSupportedVideoUrl) ?? null;
}

export function normalizeMediaType(value: unknown): MediaType {
  if (value === 'audio' || value === '仅音频') return 'audio';
  if (Array.isArray(value)) {
    return value.some((item) => normalizeMediaType(item) === 'audio') ? 'audio' : 'video';
  }
  if (value && typeof value === 'object') {
    const option = value as Record<string, unknown>;
    for (const key of ['value', 'key', 'id', 'label', 'name']) {
      if (key in option && normalizeMediaType(option[key]) === 'audio') return 'audio';
    }
  }
  return 'video';
}

async function createTicket(
  url: string,
  mediaType: MediaType,
  context: FieldContext,
): Promise<TicketResponse> {
  const response = await context.fetch(`${BACKEND_URL}/api/tickets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url,
      media_type: mediaType,
      base_signature: context.baseSignature,
      pack_id: context.packID,
      log_id: context.logID,
    }),
  });
  const text = await response.text();
  let payload: Partial<TicketResponse> & { detail?: string } = {};
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(`后端返回了无法识别的内容（HTTP ${response.status}）`);
  }
  if (!response.ok || !payload.download_url || !payload.filename) {
    throw new BackendRequestError(
      payload.detail || `生成视频附件失败（HTTP ${response.status}）`,
      response.status,
    );
  }
  return payload as TicketResponse;
}

function fieldCodeForError(error: unknown): FieldCode {
  if (!(error instanceof BackendRequestError)) return FieldCode.Error;
  if (error.status === 401 || error.status === 403) return FieldCode.AuthorizationError;
  if (error.status === 429) return FieldCode.RateLimit;
  if (error.status === 400 || error.status === 422) return FieldCode.InvalidArgument;
  return FieldCode.Error;
}

basekit.addField({
  formItems: [
    {
      key: 'source',
      label: '分享视频链接字段',
      component: FieldComponent.FieldSelect,
      props: {
        mode: 'single',
        supportType: [FieldType.Text, FieldType.Url],
      },
      validator: {
        required: true,
      },
      tooltips: [
        {
          type: 'text',
          content: '选择存放抖音、小红书、B站、快手或 TikTok 分享链接的字段',
        },
      ],
    },
    {
      key: 'mediaType',
      label: '下载内容',
      component: FieldComponent.Radio,
      props: {
        options: [
          { label: '音视频', value: 'video' },
          { label: '仅音频', value: 'audio' },
        ],
      },
      defaultValue: 'video',
      validator: {
        required: true,
      },
      tooltips: [
        {
          type: 'text',
          content: '视频超过 30 MB 时可选择仅音频，音频将转换为 M4A 附件',
        },
      ],
    },
  ],
  resultType: {
    type: FieldType.Attachment,
  },
  execute: async (formItemParams, context) => {
    try {
      const url = extractFirstUrl(formItemParams.source);
      if (!url) {
        return {
          code: FieldCode.InvalidArgument,
          msg: '没有找到支持的视频链接：文本字段可粘贴完整分享文案，URL 字段请只粘贴纯链接',
        };
      }

      const mediaType = normalizeMediaType(formItemParams.mediaType);
      console.log(JSON.stringify({
        logID: context.logID,
        mediaTypeInput: formItemParams.mediaType,
        mediaType,
      }));
      const ticket = await createTicket(url, mediaType, context);
      return {
        code: FieldCode.Success,
        data: [
          {
            name: ticket.filename,
            content: ticket.download_url,
            contentType: 'attachment/url',
          },
        ],
      };
    } catch (error) {
      console.log(JSON.stringify({
        logID: context.logID,
        error: error instanceof Error ? error.message : String(error),
      }));
      return {
        code: fieldCodeForError(error),
        msg: error instanceof Error ? error.message : '视频提取失败',
      };
    }
  },
});

export default basekit;
