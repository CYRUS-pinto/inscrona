import { View, Text, StyleSheet, TouchableOpacity, Alert, Switch } from 'react-native';
import { Card } from '@/src/components/UI/Card';
import { Button } from '@/src/components/UI/Button';
import { Input } from '@/src/components/UI/Input';
import { Badge } from '@/src/components/UI/Badge';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { api } from '@/src/api/client';
import { useAuthStore } from '@/src/store/authStore';
import { useUploadStore } from '@/src/store/uploadStore';
import { Ionicons, FontAwesome5 } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';
import * as Application from 'expo-application';

export default function SettingsScreen() {
  const router = useRouter();
  const { unpair, settings, updateSettings, backendUrl, pairingToken, isAuthenticated } = useAuthStore();
  const { pendingUploads } = useUploadStore();
  const [appVersion, setAppVersion] = useState('1.0.0');
  const [showUnpairConfirm, setShowUnpairConfirm] = useState(false);

  useEffect(() => {
    Application.getNativeApplicationVersion().then(setAppVersion).catch(() => {});
  }, []);

  const pendingCount = pendingUploads.filter(u => u.status !== 'completed').length;

  if (!isAuthenticated) {
    return (
      <View style={styles.container}>
        <Card variant="elevated" style={styles.notPairedCard}>
          <Ionicons name="link-outline" size={48} color={colors.grayLight} />
          <Text style={styles.notPairedTitle}>Not Paired</Text>
          <Text style={styles.notPairedText}>
            Pair with your laptop backend to access settings
          </Text>
          <Button title="Go to Pairing" onPress={() => router.replace('/')} />
        </Card>
      </View>
    );
  }

  const handleUnpair = async () => {
    setShowUnpairConfirm(true);
  };

  const confirmUnpair = async () => {
    await unpair();
    router.replace('/');
  };

  const testConnection = async () => {
    try {
      const health = await api.healthCheck();
      Alert.alert(
        'Connection OK',
        `Backend: ${health.status}\nOCR: ${health.models.ocr.name} (${health.models.ocr.loaded ? 'loaded' : 'idle'})\nGrading: ${health.models.grading.name} (${health.models.grading.loaded ? 'loaded' : 'idle'})`
      );
    } catch (error: any) {
      Alert.alert('Connection Failed', error.message);
    }
  };

  const exportLogs = async () => {
    Alert.alert('Export Logs', 'Log export coming soon');
  };

  const clearCache = async () => {
    Alert.alert(
      'Clear Cache',
      'This will remove all cached data and pending uploads. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Clear', style: 'destructive', onPress: () => {
          SecureStore.deleteItemAsync('inscrona_upload_queue');
          Alert.alert('Cleared', 'Cache and pending uploads cleared');
        }},
      ]
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Backend Connection */}
      <Card variant="elevated" style={styles.sectionCard}>
        <View style={styles.sectionHeader}>
          <View style={styles.sectionIcon}>
            <Ionicons name="wifi-outline" size={24} color={colors.primary} />
          </View>
          <View>
            <Text style={styles.sectionTitle}>Backend Connection</Text>
            <Text style={styles.sectionSubtitle}>Paired and ready</Text>
          </View>
        </View>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo}>
            <Text style={styles.settingLabel}>Backend URL</Text>
            <Text style={styles.settingValue} numberOfLines={1}>{backendUrl}</Text>
          </View>
        </View>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo} style={{ flex: 1 }}>
            <Text style={settings.auto_sync ? styles.settingLabel : styles.settingLabelDisabled}>Auto Sync</Text>
            <Text style={styles.settingValue}>
              {settings.auto_sync ? 'Uploads sync automatically when online' : 'Manual sync only'}
            </Text>
          </View>
          <Switch
            value={settings.auto_sync}
            onValueChange={(value) => updateSettings({ auto_sync: value })}
            trackColor={{ false: colors.grayLight, true: colors.primary }}
            thumbColor={settings.auto_sync ? colors.primaryText : colors.gray}
          />
        </View>

        <View style={styles.divider} />
        <View style={styles.actionButtons}>
          <Button title="Test Connection" variant="secondary" leftIcon={<Ionicons name="refresh-outline" size={18} />} onPress={testConnection} />
          <Button title="Unpair" variant="destructive" leftIcon={<Ionicons name="link-off-outline" size={18} />} onPress={handleUnpair} />
        </View>
      </Card>

      {/* Upload Settings */}
      <Card variant="elevated" style={styles.sectionCard}>
        <View style={styles.sectionHeader}>
          <View style={styles.sectionIcon}>
            <Ionicons name="cloud-upload-outline" size={24} color={colors.primary} />
          </View>
          <View>
            <Text style={styles.sectionTitle}>Upload & Camera</Text>
            <Text style={styles.sectionSubtitle}>
              {pendingCount > 0 ? `${pendingCount} pending uploads` : 'All uploads complete'}
            </Text>
          </View>
        </View>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo}>
            <Text style={settings.camera_quality === 'high' ? styles.settingLabel : styles.settingLabelDisabled}>Camera Quality</Text>
            <Text style={styles.settingValue}>High (best OCR accuracy)</Text>
          </View>
          <Badge variant="primary" size="sm">HIGH</Badge>
        </View>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo}>
            <Text style={styles.settingLabel}>Max Image Size</Text>
            <Text style={styles.settingValue}>{settings.max_image_size}px (resize limit)</Text>
          </View>
        </View>

        <View style={styles.divider} />
        <View style={styles.actionButtons}>
          <Button title="Clear Pending Uploads" variant="secondary" leftIcon={<Ionicons name="trash-outline" size={18} />} 
            onPress={clearCache}
            disabled={pendingCount === 0}
          />
        </View>
      </Card>

      {/* Notifications */}
      <Card variant="elevated" style={styles.sectionCard}>
        <View style={styles.sectionHeader}>
          <View style={styles.sectionIcon}>
            <Ionicons name="notifications-outline" size={24} color={colors.primary} />
          </View>
          <View>
            <Text style={styles.sectionTitle}>Notifications</Text>
            <Text style={styles.sectionSubtitle}>Push notifications for completed grades</Text>
          </View>
        </View>

        <View style={styles.settingRow}>
          <View style={styles.settingInfo} style={{ flex: 1 }}>
            <Text style={settings.notifications_enabled ? styles.settingLabel : styles.settingLabelDisabled}>Enable Notifications</Text>
            <Text style={styles.settingValue}>
              {settings.notifications_enabled ? 'Get notified when grading completes' : 'Disabled'}
            </Text>
          </View>
          <Switch
            value={settings.notifications_enabled}
            onValueChange={(value) => updateSettings({ notifications_enabled: value })}
            trackColor={{ false: colors.grayLight, true: colors.primary }}
            thumbColor={settings.notifications_enabled ? colors.primaryText : colors.gray}
          />
        </View>
      </Card>

      {/* About */}
      <Card variant="outlined" style={styles.sectionCard}>
        <View style={styles.sectionHeader}>
          <View style={styles.sectionIcon}>
            <Ionicons name="information-circle-outline" size={24} color={colors.primary} />
          </View>
          <View>
            <Text style={styles.sectionTitle}>About Inscrona</Text>
            <Text style={styles.sectionSubtitle}>Version {appVersion}</Text>
          </View>
        </View>

        <View style={styles.infoGrid}>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>OCR Engine</Text>
            <Text style={styles.infoValue}>GLM-OCR 0.9B (via Ollama)</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>Grading Model</Text>
            <Text style={styles.infoValue}>Llama 3.2:3B (via Ollama)</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>Architecture</Text>
            <Text style={styles.infoValue}>Sequential (OCR → Grade)</Text>
          </View>
          <View style={styles.infoItem}>
            <Text style={styles.infoLabel}>Storage</Text>
            <Text style={styles.infoValue}>Local (AsyncStorage + SecureStore)</Text>
          </View>
        </View>

        <View style={styles.divider} />
        <View style={styles.actionButtons}>
          <Button title="Export Logs" variant="secondary" leftIcon={<Ionicons name="download-outline" size={18} />} onPress={exportLogs} />
          <Button title="View Source" variant="ghost" leftIcon={<FontAwesome5 name="github" size={18} />} 
            onPress={() => require('expo-linking').openURL('https://github.com/CYRUS-pinto/inscrona')} />
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Built for teachers • Powered by local AI • No cloud required
          </Text>
        </View>
      </Card>
    </ScrollView>
  );
}

import { useState } from 'react';

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxxl,
    gap: spacing.lg,
  },
  sectionCard: {
    gap: spacing.md,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  sectionIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.primaryBg || colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sectionTitle: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  sectionSubtitle: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
  },
  divider: {
    height: 1,
    backgroundColor: colors.hairline,
    marginVertical: spacing.md,
  },
  settingInfo: {
    flex: 1,
    gap: 2,
  },
  settingLabel: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  settingLabelDisabled: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
  },
  settingValue: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.regular,
    color: colors.gray,
  },
  actionButtons: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  infoGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.lg,
    marginTop: spacing.md,
  },
  infoItem: {
    flex: 1,
    minWidth: 140,
    gap: spacing.xs,
  },
  infoLabel: {
    fontSize: typography.fontSize.xs,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  infoValue: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.regular,
    color: colors.ink,
  },
  footer: {
    marginTop: spacing.xl,
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
    alignItems: 'center',
  },
  footerText: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
    textAlign: 'center',
  },
  notPairedCard: {
    alignItems: 'center',
    padding: spacing.xxxl,
    margin: spacing.lg,
    gap: spacing.lg,
  },
  notPairedTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  notPairedText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
    textAlign: 'center',
  },
});