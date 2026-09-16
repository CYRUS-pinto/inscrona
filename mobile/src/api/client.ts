import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { GradeResult, PairingInfo, BackendHealth, UploadProgress, AppSettings } from '@/src/types';

const STORAGE_KEYS = {
  BACKEND_URL: 'inscrona_backend_url',
  PAIRING_TOKEN: 'inscrona_pairing_token',
  SETTINGS: 'inscrona_settings',
} as const;

class ApiClient {
  private baseUrl: string = '';
  private token: string = '';
  private ws: WebSocket | null = null;
  private listeners: Map<string, (progress: UploadProgress) => void> = new Map();

  async initialize(): Promise<void> {
    this.baseUrl = (await SecureStore.getItemAsync(STORAGE_KEYS.BACKEND_URL)) || '';
    this.token = (await SecureStore.getItemAsync(STORAGE_KEYS.PAIRING_TOKEN)) || '';
  }

  async setBackend(url: string, token: string): Promise<void> {
    this.baseUrl = url.replace(/\/$/, '');
    this.token = token;
    await SecureStore.setItemAsync(STORAGE_KEYS.BACKEND_URL, this.baseUrl);
    await SecureStore.setItemAsync(STORAGE_KEYS.PAIRING_TOKEN, this.token);
  }

  async clearBackend(): Promise<void> {
    this.baseUrl = '';
    this.token = '';
    await SecureStore.deleteItemAsync(STORAGE_KEYS.BACKEND_URL);
    await SecureStore.deleteItemAsync(STORAGE_KEYS.PAIRING_TOKEN);
  }

  getBackendUrl(): string {
    return this.baseUrl;
  }

  getToken(): string {
    return this.token;
  }

  isPaired(): boolean {
    return !!(this.baseUrl && this.token);
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    if (!this.baseUrl) throw new Error('Backend not paired');
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.token && { Authorization: `Bearer ${this.token}` }),
      ...options.headers,
    };

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async healthCheck(): Promise<BackendHealth> {
    return this.request<BackendHealth>('/health');
  }

  async getPairingInfo(): Promise<PairingInfo> {
    return this.request<PairingInfo>('/api/pair');
  }

  async gradeImage(imageUri: string, rubric: string): Promise<GradeResult> {
    const formData = new FormData();
    
    const fileName = imageUri.split('/').pop() || `image_${Date.now()}.jpg`;
    const mimeType = fileName.endsWith('.heic') || fileName.endsWith('.HEIC') ? 'image/heic' : 'image/jpeg';
    
    formData.append('file', {
      uri: imageUri,
      name: fileName,
      type: mimeType,
    } as any);
    formData.append('rubric', rubric);

    const response = await fetch(`${this.baseUrl}/grade`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Grading failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getResults(): Promise<GradeResult[]> {
    const data = await this.request<{ results: GradeResult[] }>('/results');
    return data.results;
  }

  async getResult(id: string): Promise<GradeResult> {
    return this.request<GradeResult>(`/results/${id}`);
  }

  async exportCsv(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/results/export.csv`, {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    return response.text();
  }

  connectProgress(uploadId: string, onProgress: (progress: UploadProgress) => void): () => void {
    this.listeners.set(uploadId, onProgress);
    
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
      this.connectWebSocket();
    }

    return () => {
      this.listeners.delete(uploadId);
      if (this.listeners.size === 0 && this.ws) {
        this.ws.close();
        this.ws = null;
      }
    };
  }

  private connectWebSocket(): void {
    if (!this.baseUrl) return;
    
    const wsUrl = this.baseUrl.replace('http', 'ws') + '/ws/progress';
    this.ws = new WebSocket(wsUrl);

    this.ws.onmessage = (event) => {
      try {
        const progress: UploadProgress = JSON.parse(event.data);
        const listener = this.listeners.get(progress.stage === 'completed' ? progress.result?.id : '');
        if (listener) listener(progress);
      } catch (e) {
        console.warn('Invalid progress message:', e);
      }
    };

    this.ws.onerror = (error) => {
      console.warn('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      setTimeout(() => this.connectWebSocket(), 5000);
    };
  }

  async getSettings(): Promise<AppSettings> {
    const stored = await SecureStore.getItemAsync(STORAGE_KEYS.SETTINGS);
    return stored ? JSON.parse(stored) : this.getDefaultSettings();
  }

  async saveSettings(settings: Partial<AppSettings>): Promise<void> {
    const current = await this.getSettings();
    const updated = { ...current, ...settings };
    await SecureStore.setItemAsync(STORAGE_KEYS.SETTINGS, JSON.stringify(updated));
  }

  private getDefaultSettings(): AppSettings {
    return {
      backend_url: this.baseUrl,
      pairing_token: this.token,
      auto_sync: true,
      notifications_enabled: true,
      camera_quality: 'high',
      max_image_size: 2000,
    };
  }
}

export const api = new ApiClient();