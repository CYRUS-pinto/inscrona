import { Stack } from 'expo-router';
import { Providers } from '@/src/components/Providers';
import { useAuthStore } from '@/src/store/authStore';
import { useEffect } from 'react';
import { SplashScreen } from 'expo-splash-screen';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const { initialize, isAuthenticated } = useAuthStore();

  useEffect(() => {
    initialize().finally(() => SplashScreen.hideAsync());
  }, [initialize]);

  return (
    <Providers>
      <Stack
        screenOptions={{
          headerShown: false,
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" options={{ presentation: 'modal' }} />
        <Stack.Screen name="(tabs)/_layout" options={{ presentation: 'card' }} />
        <Stack.Screen name="camera" options={{ presentation: 'fullScreenModal' }} />
        <Stack.Screen name="review/[id]" options={{ presentation: 'card' }} />
        <Stack.Screen name="processing/[id]" options={{ presentation: 'card' }} />
        <Stack.Screen name="result/[id]" options={{ presentation: 'card' }} />
        <Stack.Screen name="settings" options={{ presentation: 'card' }} />
      </Stack>
    </Providers>
  );
}