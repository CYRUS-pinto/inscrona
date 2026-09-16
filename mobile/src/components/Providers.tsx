'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import * as SecureStore from 'expo-secure-store';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { SentryProvider } from 'expo-sentry';
import { Platform } from 'react-native';
import { useEffect, useMemo, useState } from 'react';
import { useAuthStore } from '@/src/store/authStore';
import { useUploadStore } from '@/src/store/uploadStore';
import { api } from '@/src/api/client';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const persister = createSyncStoragePersister({
  storage: {
    getItem: async (key) => {
      const value = await SecureStore.getItemAsync(key);
      return value ?? null;
    },
    setItem: async (key, value) => {
      await SecureStore.setItemAsync(key, value);
    },
    removeItem: async (key) => {
      await SecureStore.deleteItemAsync(key);
    },
  },
  dehydrateOptions: { shouldDehydrate: () => true },
});

export function Providers({ children }: { children: React.ReactNode }) {
  const { initialize, isAuthenticated, isInitialized } = useAuthStore();
  const processQueue = useUploadStore((s) => s.processQueue);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    initialize().then(() => setMounted(true));
  }, [initialize]);

  useEffect(() => {
    if (isAuthenticated) {
      processQueue();
      const interval = setInterval(processQueue, 30000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, processQueue]);

  if (!mounted) {
    return null;
  }

  return (
    <SentryProvider>
      <QueryClientProvider client={queryClient}>
        <PersistQueryClientProvider client={queryClient} persister={persister} maxAge={1000 * 60 * 60 * 24}>
          {children}
          {__DEV__ && <ReactQueryDevtools initialIsOpen={false} />}
        </PersistQueryClientProvider>
      </QueryClientProvider>
    </SentryProvider>
  );
}