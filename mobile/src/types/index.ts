export interface GradeResult {
  id: string;
  marks: number;
  confidence: number;
  feedback: string;
  ocr_text: string;
  rubric: string;
  image_url?: string;
  created_at: string;
  processing_time_ms: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress_stage?: 'uploading' | 'ocr' | 'grading' | 'saving';
}

export interface PairingInfo {
  url: string;
  token: string;
  expires_at: string;
  qr_data: string;
}

export interface BackendHealth {
  status: 'ok' | 'degraded';
  models: {
    ocr: { name: string; loaded: boolean };
    grading: { name: string; loaded: boolean };
  };
  version: string;
}

export interface UploadProgress {
  stage: 'uploading' | 'ocr' | 'grading' | 'saving' | 'completed' | 'error';
  progress: number; // 0-100
  message: string;
  result?: GradeResult;
  error?: string;
}

export interface PendingUpload {
  id: string;
  image_uri: string;
  rubric: string;
  created_at: string;
  status: 'queued' | 'uploading' | 'failed';
  retry_count: number;
}

export interface AppSettings {
  backend_url: string;
  pairing_token: string;
  auto_sync: boolean;
  notifications_enabled: boolean;
  camera_quality: 'high' | 'medium' | 'low';
  max_image_size: number;
}

export type RootStackParamList = {
  index: undefined;
  '(tabs)': undefined;
  camera: undefined;
  'review/[id]': { id: string };
  'processing/[id]': { id: string };
  'result/[id]': { id: string };
  history: undefined;
  settings: undefined;
};

declare global {
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}