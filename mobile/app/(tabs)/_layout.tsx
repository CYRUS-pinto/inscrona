import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing } from '@/src/utils/theme';
import { useAuthStore } from '@/src/store/authStore';
import { useUploadStore } from '@/src/store/uploadStore';

export default function TabsLayout() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const pendingCount = useUploadStore((s) => s.pendingUploads.filter(u => u.status !== 'completed').length);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.gray,
        tabBarStyle: {
          backgroundColor: colors.canvas,
          borderTopWidth: 1,
          borderTopColor: colors.hairline,
          paddingBottom: spacing.sm,
          height: 80,
        },
        tabBarLabelStyle: {
          fontSize: 11,
          fontFamily: 'Inter_500Medium',
        },
      }}
    >
      <Tabs.Screen
        name="camera"
        options={{
          title: 'Scan',
          tabBarIcon: ({ focused }) => (
            <Ionicons name={focused ? 'camera' : 'camera-outline'} size={26} color={focused ? colors.primary : colors.gray} />
          ),
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'History',
          tabBarIcon: ({ focused }) => (
            <Ionicons name={focused ? 'time' : 'time-outline'} size={26} color={focused ? colors.primary : colors.gray} />
          ),
          tabBarBadge: pendingCount > 0 ? String(pendingCount) : undefined,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ focused }) => (
            <Ionicons name={focused ? 'settings' : 'settings-outline'} size={26} color={focused ? colors.primary : colors.gray} />
          ),
        }}
      />
    </Tabs>
  );
}