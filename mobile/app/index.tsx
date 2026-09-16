import { View, Text, StyleSheet, Image, ActivityIndicator, Alert } from 'react-native';
import { BarCodeScanner } from 'expo-barcode-scanner';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Button } from '@/src/components/UI/Button';
import { Card } from '@/src/components/UI/Card';
import { Input } from '@/src/components/UI/Input';
import { Progress } from '@/src/components/UI/Progress';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useEffect, useState, useRef } from 'react';
import { api } from '@/src/api/client';
import * as SecureStore from 'expo-secure-store';

const STITCH_DEEPLINK = 'inscrona://pair';

export default function PairingScreen() {
  const router = useRouter();
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [scanned, setScanned] = useState(false);
  const [manualUrl, setManualUrl] = useState('');
  const [manualToken, setManualToken] = useState('');
  const [pairing, setPairing] = useState(false);
  const [error, setError] = useState('');
  const scannerRef = useRef<BarCodeScanner>(null);

  useEffect(() => {
    (async () => {
      const { status } = await CameraView.requestCameraPermissionsAsync();
      setHasPermission(status === 'granted');
    })();
  }, []);

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (scanned) return;
    setScanned(true);

    try {
      const url = new URL(data);
      if (url.protocol === 'inscrona:' && url.hostname === 'pair') {
        const backendUrl = url.searchParams.get('url');
        const token = url.searchParams.get('token');
        if (backendUrl && token) {
          await pairWithBackend(backendUrl, token);
        } else {
          throw new Error('Invalid pairing QR code');
        }
      } else {
        throw new Error('Not a valid Inscrona pairing code');
      }
    } catch {
      Alert.alert('Invalid QR Code', 'This does not appear to be a valid Inscrona pairing code.');
      setScanned(false);
    }
  };

  const pairWithBackend = async (url: string, token: string) => {
    setPairing(true);
    setError('');
    try {
      // Verify the backend is reachable
      const testApi = new (await import('@/src/api/client')).ApiClient();
      await testApi.setBackend(url, token);
      const health = await testApi.healthCheck();
      
      if (health.status !== 'ok' && health.status !== 'degraded') {
        throw new Error('Backend health check failed');
      }

      // Save pairing
      const { useAuthStore } = await import('@/src/store/authStore');
      useAuthStore.getState().pair(url, token);
      
      router.replace('/(tabs)/camera');
    } catch (err: any) {
      setError(err.message || 'Failed to pair with backend');
    } finally {
      setPairing(false);
    }
  };

  const handleManualPair = async () => {
    if (!manualUrl.trim() || !manualToken.trim()) {
      setError('Please enter both backend URL and pairing token');
      return;
    }
    await pairWithBackend(manualUrl.trim(), manualToken.trim());
  };

  if (hasPermission === null) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Requesting camera permission...</Text>
      </View>
    );
  }

  if (!hasPermission) {
    return (
      <View style={styles.container}>
        <Card variant="elevated" style={styles.errorCard}>
          <Text style={styles.errorTitle}>Camera Permission Required</Text>
          <Text style={styles.errorText}>
            Inscrona needs camera access to scan the pairing QR code from your laptop.
          </Text>
          <Button title="Open Settings" onPress={() => require('expo-linking').openSettings()} />
        </Card>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Inscrona</Text>
        <Text style={styles.subtitle}>Pair with your laptop to start grading</Text>
      </View>

      <Card variant="elevated" style={styles.scannerCard}>
        {hasPermission && !scanned && (
          <View style={styles.scannerWrapper}>
            <BarCodeScanner
              ref={scannerRef}
              onBarCodeScanned={handleBarCodeScanned}
              barCodeTypes={['qr']}
              style={styles.scanner}
            />
            <View style={styles.scanOverlay}>
              <View style={styles.scanFrame} />
              <Text style={styles.scanHint}>Align QR code within frame</Text>
            </View>
          </View>
        )}
      </Card>

      <View style={styles.divider}>
        <View style={styles.dividerLine} />
        <Text style={styles.dividerText}>OR</Text>
        <View style={styles.dividerLine} />
      </View>

      <Card variant="outlined" style={styles.manualCard}>
        <Text style={styles.manualTitle}>Manual Pairing</Text>
        <Text style={styles.manualText}>
          Enter the backend URL and token shown on your laptop
        </Text>
        
        <Input
          label="Backend URL"
          placeholder="https://xxx.pinggy.link"
          value={manualUrl}
          onChangeText={setManualUrl}
          keyboardType="url"
          autoCapitalize="none"
        />
        
        <Input
          label="Pairing Token"
          placeholder="abc123..."
          value={manualToken}
          onChangeText={setManualToken}
          secureTextEntry
          autoCapitalize="none"
        />

        {error && <Text style={styles.errorText}>{error}</Text>}

        <Button
          title={pairing ? 'Pairing...' : 'Connect'}
          onPress={handleManualPair}
          disabled={pairing}
          fullWidth
        />
      </Card>

      <View style={styles.footer}>
        <Text style={styles.footerText}>
          Run <Text style={styles.code}>python start.py</Text> on your laptop to see the pairing QR code
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
    padding: spacing.lg,
    justifyContent: 'space-between',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
  },
  loadingText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  title: {
    fontSize: typography.fontSize['4xl'],
    fontFamily: typography.fontFamily.bold,
    color: colors.navy,
  },
  subtitle: {
    fontSize: typography.fontSize.lg,
    color: colors.gray,
    marginTop: spacing.xs,
  },
  scannerCard: {
    overflow: 'hidden',
    marginBottom: spacing.lg,
  },
  scannerWrapper: {
    position: 'relative',
    aspectRatio: 1,
  },
  scanner: {
    flex: 1,
  },
  scanOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanFrame: {
    width: 200,
    height: 200,
    borderWidth: 3,
    borderColor: colors.primary,
    borderRadius: radius.md,
    borderStyle: 'dashed',
  },
  scanHint: {
    position: 'absolute',
    bottom: spacing.xl,
    fontSize: typography.fontSize.base,
    color: colors.gray,
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginVertical: spacing.lg,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: colors.hairline,
  },
  dividerText: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  manualCard: {
    gap: spacing.md,
  },
  manualTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  manualText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
  },
  errorText: {
    fontSize: typography.fontSize.sm,
    color: colors.error,
  },
  footer: {
    alignItems: 'center',
    paddingTop: spacing.lg,
  },
  footerText: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
    textAlign: 'center',
  },
  code: {
    fontFamily: typography.fontFamily.mono,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radius.xs,
  },
  errorCard: {
    alignItems: 'center',
    padding: spacing.xl,
  },
  errorTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
    marginBottom: spacing.sm,
  },
});