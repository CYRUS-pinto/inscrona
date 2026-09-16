import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { PendingUpload, GradeResult } from '@/src/types';
import { api } from '@/src/api/client';
import * as FileSystem from 'expo-file-system';

interface UploadState {
  pendingUploads: PendingUpload[];
  completedResults: GradeResult[];
  addToQueue: (imageUri: string, rubric: string) => Promise<string>;
  processQueue: () => Promise<void>;
  retryUpload: (id: string) => Promise<void>;
  removeFromQueue: (id: string) => void;
  clearCompleted: () => void;
  getUpload: (id: string) => PendingUpload | undefined;
}

const MAX_RETRIES = 3;

export const useUploadStore = create<UploadState>()(
  persist(
    (set, get) => ({
      pendingUploads: [],
      completedResults: [],

      addToQueue: async (imageUri: string, rubric: string) => {
        const id = `upload_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        const upload: PendingUpload = {
          id,
          image_uri: imageUri,
          rubric,
          created_at: new Date().toISOString(),
          status: 'queued',
          retry_count: 0,
        };

        set((state) => ({
          pendingUploads: [...state.pendingUploads, upload],
        }));

        return id;
      },

      processQueue: async () => {
        const queued = get().pendingUploads.filter(
          (u) => u.status === 'queued' || (u.status === 'failed' && u.retry_count < MAX_RETRIES)
        );

        for (const upload of queued) {
          if (!api.isPaired()) break;

          set((state) => ({
            pendingUploads: state.pendingUploads.map((u) =>
              u.id === upload.id ? { ...u, status: 'uploading' as const } : u
            ),
          }));

          try {
            const result = await api.gradeImage(upload.image_uri, upload.rubric);
            
            set((state) => ({
              pendingUploads: state.pendingUploads.filter((u) => u.id !== upload.id),
              completedResults: [result, ...state.completedResults].slice(0, 100),
            }));

            // Clean up local file
            try {
              await FileSystem.deleteAsync(upload.image_uri, { idempotent: true });
            } catch {}
          } catch (error) {
            set((state) => ({
              pendingUploads: state.pendingUploads.map((u) =>
                u.id === upload.id
                  ? { ...u, status: 'failed' as const, retry_count: u.retry_count + 1 }
                  : u
              ),
            }));
          }
        }
      },

      retryUpload: async (id: string) => {
        const upload = get().pendingUploads.find((u) => u.id === id);
        if (!upload) return;

        set((state) => ({
          pendingUploads: state.pendingUploads.map((u) =>
            u.id === id ? { ...u, status: 'queued' as const, retry_count: 0 } : u
          ),
        }));

        await get().processQueue();
      },

      removeFromQueue: (id: string) => {
        set((state) => ({
          pendingUploads: state.pendingUploads.filter((u) => u.id !== id),
        }));
      },

      clearCompleted: () => {
        set({ completedResults: [] });
      },

      getUpload: (id: string) => {
        return get().pendingUploads.find((u) => u.id === id);
      },
    }),
    {
      name: 'upload-storage',
      partialize: (state) => ({
        pendingUploads: state.pendingUploads,
        completedResults: state.completedResults,
      }),
    }
  )
);