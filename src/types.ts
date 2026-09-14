export type ProcessingScope = 'record' | 'view' | 'table';

export interface FieldOption {
  id: string;
  name: string;
}

export interface LogEntry {
  id: string;
  type: 'success' | 'skip' | 'error' | 'info';
  message: string;
  time: string;
}

export interface ProgressState {
  current: number;
  total: number;
  success: number;
  skipped: number;
  failed: number;
}
