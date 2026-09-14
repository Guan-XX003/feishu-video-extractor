import { bitable, FieldType } from '@lark-base-open/js-sdk';
import type { FieldOption, ProcessingScope } from './types';

export interface LarkContext {
  table: Awaited<ReturnType<typeof bitable.base.getTableById>>;
  tableId: string;
  viewId?: string;
  recordId?: string;
  sourceFields: FieldOption[];
  attachmentFields: FieldOption[];
}

export async function loadLarkContext(): Promise<LarkContext> {
  const selection = await bitable.base.getSelection();
  if (!selection.tableId) {
    throw new Error('请先在多维表格中选择一个数据表');
  }

  const table = await bitable.base.getTableById(selection.tableId);
  const fields = await table.getFieldList();
  const sourceFields: FieldOption[] = [];
  const attachmentFields: FieldOption[] = [];

  for (const field of fields) {
    const [name, type] = await Promise.all([field.getName(), field.getType()]);
    if (type === FieldType.Text || type === FieldType.Url || type === FieldType.Phone) {
      sourceFields.push({ id: field.id, name });
    }
    if (type === FieldType.Attachment) {
      attachmentFields.push({ id: field.id, name });
    }
  }

  return {
    table,
    tableId: selection.tableId,
    viewId: selection.viewId ?? undefined,
    recordId: selection.recordId ?? undefined,
    sourceFields,
    attachmentFields,
  };
}

export async function createDefaultFields(context: LarkContext): Promise<LarkContext> {
  const fieldList = await context.table.getFieldList();
  let sourceField = context.sourceFields.find((field) => field.name === '分享链接');
  let attachmentField = context.attachmentFields.find((field) => field.name === '视频附件');

  if (!sourceField) {
    const id = await context.table.addField({ name: '分享链接', type: FieldType.Text });
    sourceField = { id, name: '分享链接' };
  }
  if (!attachmentField) {
    const id = await context.table.addField({ name: '视频附件', type: FieldType.Attachment });
    attachmentField = { id, name: '视频附件' };
  }

  const refreshed = await loadLarkContext();
  return {
    ...refreshed,
    sourceFields: refreshed.sourceFields.length ? refreshed.sourceFields : [sourceField],
    attachmentFields: refreshed.attachmentFields.length ? refreshed.attachmentFields : [attachmentField],
  };
}

export async function getRecordIds(context: LarkContext, scope: ProcessingScope): Promise<string[]> {
  if (scope === 'record') {
    if (!context.recordId) {
      throw new Error('请先在表格中选中一条记录');
    }
    return [context.recordId];
  }

  if (scope === 'view') {
    if (!context.viewId) {
      throw new Error('当前未选择视图');
    }
    const view = await context.table.getViewById(context.viewId);
    const visibleRecordIds = await view.getVisibleRecordIdList();
    return visibleRecordIds.filter((recordId): recordId is string => Boolean(recordId));
  }

  const result = await context.table.getRecords({ pageSize: 5000 });
  return result.records
    .map((record) => record.recordId)
    .filter((recordId): recordId is string => Boolean(recordId));
}

export async function readCellText(
  context: LarkContext,
  fieldId: string,
  recordId: string,
): Promise<string> {
  return context.table.getCellString(fieldId, recordId);
}

export async function hasAttachment(
  context: LarkContext,
  fieldId: string,
  recordId: string,
): Promise<boolean> {
  const value = await context.table.getCellValue(fieldId, recordId);
  return Array.isArray(value) && value.length > 0;
}

export async function writeAttachment(
  context: LarkContext,
  fieldId: string,
  recordId: string,
  file: File,
): Promise<void> {
  const field = await context.table.getFieldById(fieldId);
  await field.setValue(recordId, file);
}
