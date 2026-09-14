import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  CircleMinus,
  Download,
  FileVideo2,
  Link2,
  LoaderCircle,
  Paperclip,
  Plus,
  XCircle,
} from 'lucide-react';
import {
  createDefaultFields,
  getRecordIds,
  hasAttachment,
  loadLarkContext,
  readCellText,
  writeAttachment,
  type LarkContext,
} from './lark';
import type { FieldOption, LogEntry, ProcessingScope, ProgressState } from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const initialProgress: ProgressState = {
  current: 0,
  total: 0,
  success: 0,
  skipped: 0,
  failed: 0,
};

function extractFirstUrl(value: string): string | null {
  const match = value.match(/https?:\/\/[^\s]+/i);
  return match?.[0].replace(/[)\]）。，,]+$/u, '') ?? null;
}

function now(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}

function filenameFromDisposition(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) return decodeURIComponent(encoded);
  const basic = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return basic || fallback;
}

async function fetchVideo(url: string, signal: AbortSignal): Promise<File> {
  const response = await fetch(`${API_BASE_URL}/api/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `下载失败（HTTP ${response.status}）`);
  }

  const blob = await response.blob();
  const fileName = filenameFromDisposition(
    response.headers.get('content-disposition'),
    `video-${Date.now()}.mp4`,
  );
  return new File([blob], fileName, { type: blob.type || 'video/mp4' });
}

function FieldSelect({
  label,
  icon,
  options,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  icon: 'link' | 'attachment';
  options: FieldOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const Icon = icon === 'link' ? Link2 : Paperclip;
  return (
    <label className="field-group">
      <span className="field-label">{label}</span>
      <span className="select-shell">
        <Icon size={18} strokeWidth={1.8} />
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">{placeholder}</option>
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
        <ChevronDown className="select-chevron" size={18} />
      </span>
    </label>
  );
}

function StatusIcon({ type }: { type: LogEntry['type'] }) {
  if (type === 'success') return <CheckCircle2 className="status-success" size={18} />;
  if (type === 'skip') return <CircleMinus className="status-skip" size={18} />;
  if (type === 'error') return <XCircle className="status-error" size={18} />;
  return <LoaderCircle className="status-info" size={18} />;
}

export default function App() {
  const [context, setContext] = useState<LarkContext | null>(null);
  const [sourceFieldId, setSourceFieldId] = useState('');
  const [attachmentFieldId, setAttachmentFieldId] = useState('');
  const [scope, setScope] = useState<ProcessingScope>('record');
  const [progress, setProgress] = useState<ProgressState>(initialProgress);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [message, setMessage] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const progressPercent = useMemo(() => {
    if (!progress.total) return 0;
    return Math.round((progress.current / progress.total) * 100);
  }, [progress]);

  const addLog = (type: LogEntry['type'], messageText: string) => {
    setLogs((current) => [
      { id: `${Date.now()}-${Math.random()}`, type, message: messageText, time: now() },
      ...current,
    ].slice(0, 40));
  };

  useEffect(() => {
    let mounted = true;
    const initialize = async () => {
      if (DEMO_MODE) {
        const demoContext = {
          table: {} as LarkContext['table'],
          tableId: 'demo-table',
          recordId: 'demo-record',
          viewId: 'demo-view',
          sourceFields: [{ id: 'share-url', name: '分享链接' }],
          attachmentFields: [{ id: 'video-attachment', name: '视频附件' }],
        };
        if (mounted) {
          setContext(demoContext);
          setSourceFieldId('share-url');
          setAttachmentFieldId('video-attachment');
          setInitializing(false);
        }
        return;
      }

      try {
        const nextContext = await loadLarkContext();
        if (!mounted) return;
        setContext(nextContext);
        setSourceFieldId(
          nextContext.sourceFields.find((field) => field.name === '分享链接')?.id ||
            nextContext.sourceFields[0]?.id ||
            '',
        );
        setAttachmentFieldId(
          nextContext.attachmentFields.find((field) => field.name === '视频附件')?.id ||
            nextContext.attachmentFields[0]?.id ||
            '',
        );
      } catch (error) {
        setMessage(error instanceof Error ? error.message : '无法连接飞书多维表格');
      } finally {
        if (mounted) setInitializing(false);
      }
    };
    void initialize();
    return () => {
      mounted = false;
      abortRef.current?.abort();
    };
  }, []);

  const handleCreateFields = async () => {
    if (!context || DEMO_MODE) return;
    setLoading(true);
    try {
      const nextContext = await createDefaultFields(context);
      setContext(nextContext);
      setSourceFieldId(nextContext.sourceFields.find((field) => field.name === '分享链接')?.id || '');
      setAttachmentFieldId(
        nextContext.attachmentFields.find((field) => field.name === '视频附件')?.id || '',
      );
      setMessage('字段初始化完成');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '字段初始化失败');
    } finally {
      setLoading(false);
    }
  };

  const runDemo = async () => {
    setLoading(true);
    setLogs([]);
    setProgress({ current: 0, total: 12, success: 0, skipped: 0, failed: 0 });
    for (let index = 1; index <= 12; index += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 120));
      const skipped = index === 5;
      const failed = index === 9;
      setProgress((current) => ({
        current: index,
        total: 12,
        success: current.success + (skipped || failed ? 0 : 1),
        skipped: current.skipped + (skipped ? 1 : 0),
        failed: current.failed + (failed ? 1 : 0),
      }));
      addLog(
        skipped ? 'skip' : failed ? 'error' : 'success',
        skipped
          ? `跳过：第 ${index} 条记录（已有附件）`
          : failed
            ? `失败：第 ${index} 条记录（无法解析链接）`
            : `成功提取：第 ${index} 条记录`,
      );
    }
    setLoading(false);
  };

  const handleStart = async () => {
    if (DEMO_MODE) {
      await runDemo();
      return;
    }
    if (!context || !sourceFieldId || !attachmentFieldId) {
      setMessage('请选择分享链接字段和视频附件字段');
      return;
    }

    setLoading(true);
    setMessage('');
    setLogs([]);
    setProgress(initialProgress);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const recordIds = await getRecordIds(context, scope);
      setProgress({ ...initialProgress, total: recordIds.length });

      for (let index = 0; index < recordIds.length; index += 1) {
        if (controller.signal.aborted) break;
        const recordId = recordIds[index];
        const rowNumber = index + 1;
        try {
          if (await hasAttachment(context, attachmentFieldId, recordId)) {
            setProgress((current) => ({
              ...current,
              current: rowNumber,
              skipped: current.skipped + 1,
            }));
            addLog('skip', `跳过：第 ${rowNumber} 条记录（已有附件）`);
            continue;
          }

          const rawValue = await readCellText(context, sourceFieldId, recordId);
          const url = extractFirstUrl(rawValue.trim());
          if (!url) {
            setProgress((current) => ({
              ...current,
              current: rowNumber,
              skipped: current.skipped + 1,
            }));
            addLog('skip', `跳过：第 ${rowNumber} 条记录（未找到有效链接）`);
            continue;
          }

          const file = await fetchVideo(url, controller.signal);
          await writeAttachment(context, attachmentFieldId, recordId, file);
          setProgress((current) => ({
            ...current,
            current: rowNumber,
            success: current.success + 1,
          }));
          addLog('success', `成功提取：第 ${rowNumber} 条记录`);
        } catch (error) {
          setProgress((current) => ({
            ...current,
            current: rowNumber,
            failed: current.failed + 1,
          }));
          addLog(
            'error',
            `失败：第 ${rowNumber} 条记录（${error instanceof Error ? error.message : '未知错误'}）`,
          );
        }
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '处理失败');
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  if (initializing) {
    return (
      <main className="app-shell loading-shell">
        <LoaderCircle className="spin" size={24} />
        <span>正在连接多维表格…</span>
      </main>
    );
  }

  const hasRequiredFields = Boolean(context?.sourceFields.length && context?.attachmentFields.length);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="title-icon"><FileVideo2 size={20} /></div>
        <div>
          <h1>视频链接提取</h1>
          <p>从分享链接解析视频并回填附件字段</p>
        </div>
      </header>

      {!hasRequiredFields && !DEMO_MODE && (
        <section className="empty-fields">
          <p>当前数据表缺少文本字段或附件字段。</p>
          <button type="button" className="secondary-button" onClick={handleCreateFields} disabled={loading}>
            <Plus size={16} /> 初始化“分享链接”和“视频附件”字段
          </button>
        </section>
      )}

      <section className="form-section">
        <FieldSelect
          label="分享链接字段"
          icon="link"
          options={context?.sourceFields || []}
          value={sourceFieldId}
          onChange={setSourceFieldId}
          placeholder="请选择文本或链接字段"
        />
        <FieldSelect
          label="视频附件字段"
          icon="attachment"
          options={context?.attachmentFields || []}
          value={attachmentFieldId}
          onChange={setAttachmentFieldId}
          placeholder="请选择附件字段"
        />

        <fieldset className="scope-group">
          <legend>处理范围</legend>
          {([
            ['record', '当前记录'],
            ['view', '当前视图'],
            ['table', '全表未处理记录'],
          ] as Array<[ProcessingScope, string]>).map(([value, label]) => (
            <label key={value} className="radio-row">
              <input
                type="radio"
                name="scope"
                value={value}
                checked={scope === value}
                onChange={() => setScope(value)}
              />
              <span>{label}</span>
            </label>
          ))}
        </fieldset>

        <button
          type="button"
          className="primary-button"
          onClick={handleStart}
          disabled={loading || !sourceFieldId || !attachmentFieldId}
        >
          {loading ? <LoaderCircle className="spin" size={18} /> : <Download size={18} />}
          {loading ? '正在提取' : '开始提取'}
        </button>
        {message && <p className="inline-message">{message}</p>}
      </section>

      {(progress.total > 0 || loading) && (
        <section className="progress-panel">
          <div className="progress-heading">
            <strong>正在处理 {progress.current} / {progress.total}</strong>
            <span>{progressPercent}%</span>
          </div>
          <div className="progress-track" aria-label={`处理进度 ${progressPercent}%`}>
            <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="progress-stats">
            <span><i className="dot success-dot" />成功 {progress.success}</span>
            <span><i className="dot skip-dot" />跳过 {progress.skipped}</span>
            <span><i className="dot error-dot" />失败 {progress.failed}</span>
          </div>
        </section>
      )}

      <section className="log-section">
        <div className="section-heading">
          <h2>状态日志</h2>
          {logs.length > 0 && (
            <button type="button" className="text-button" onClick={() => setLogs([])}>清空日志</button>
          )}
        </div>
        <div className="log-list">
          {logs.length === 0 ? (
            <p className="empty-log">任务开始后，这里会显示每条记录的处理结果。</p>
          ) : (
            logs.map((entry) => (
              <div className="log-row" key={entry.id}>
                <StatusIcon type={entry.type} />
                <span className="log-message">{entry.message}</span>
                <time>{entry.time}</time>
              </div>
            ))
          )}
        </div>
      </section>

      <footer className="safety-note">
        <AlertTriangle size={18} />
        <span>仅处理有权下载的公开、无 DRM 视频</span>
      </footer>
    </main>
  );
}
