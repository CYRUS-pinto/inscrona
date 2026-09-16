import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/src/api/client';
import { AppSettings } from '@/src/types';

interface AuthState {
  isAuthenticated: boolean;
  isInitialized: boolean;
  backendUrl: string;
  pairingToken: string;
  settings: AppSettings;
  initialize: () => Promise<void>;
  pair: (url: string, token: string) => Promise<void>;
  unpair: () => Promise<void>;
  updateSettings: (settings: Partial<AppSettings>) => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      isInitialized: false,
      backendUrl: '',
      pairingToken: '',
      settings: {
        backend_url: '',
        pairing_token: '',
        auto_sync: true,
        notifications_enabled: true,
        camera_quality: 'high',
        max_image_size: 2000,
      },

      initialize: async () => {
        await api.initialize();
        const url = api.getBackendUrl();
        const token = api.getToken();
        const settings = await api.getSettings();
        
        set({
          isInitialized: true,
          isAuthenticated: api.isPaired(),
          backendUrl: url,
          pairingToken: token,
          settings,
        });
      },

      pair: async (url: string, token: string) => {
        await api.setBackend(url, token);
        const settings = await api.getSettings();
        set({
          isAuthenticated: true,
          backendUrl: url,
          pairingToken: token,
          settings,
        });
      },

      unpair: async () => {
        await api.clearBackend();
        set({
          isAuthenticated: false,
          backendUrl: '',
          pairingToken: '',
          settings: { ...get().settings, backend_url: '', pairing_token: '' },
        });
      },

      updateSettings: async (newSettings: Partial<AppSettings>) => {
        await api.saveSettings(newSettings);
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }));
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        backendUrl: state.backendUrl,
        pairingToken: state.pairingToken,
        settings: state.settings,
      }),
    }
  )
);