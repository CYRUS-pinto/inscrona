import { View, Text, StyleSheet, Alert, ActivityIndicator, TouchableOpacity, Image } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { Button } from '@/src/components/UI/Button';
import { Card } from '@/src/components/UI/Card';
import { Input } from '@/src/components/UI/Input';
import { Progress } from '@/src/components/UI/Progress';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter, useNavigation } from 'expo-router';
import { useEffect, useState, useRef, useCallback } from 'react';
import { api } from '@/src/api/client';
import { useUploadStore } from '@/src/store/uploadStore';
import { Ionicons } from '@expo/vector-icons';

const RUBRIC_DEFAULT = 'Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity.';

export default function CameraScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [mode, setMode] = useState<'camera' | 'gallery'>('camera');
  const [rubric, setRubric] = useState(RUBRIC_DEFAULT);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const cameraRef = useRef<CameraView>(null);
  const { addToQueue, processQueue } = useUploadStore();

  useEffect(() => {
    (async () => {
      const { status } = await CameraView.requestCameraPermissionsAsync();
      setHasPermission(status === 'granted');
    })();
  }, []);

  const takePicture = useCallback(async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.9,
        base64: false,
        skipProcessing: false,
      });
      if (photo?.uri) {
        setCapturedImage(photo.uri);
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to capture image');
    }
  }, []);

  const pickFromGallery = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 0.9,
        base64: false,
      });
      if (!result.canceled && result.assets[0]?.uri) {
        setCapturedImage(result.assets[0].uri);
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to select image');
    }
  };

  const handleUpload = async () => {
    if (!capturedImage) return;
    setUploading(true);
    setUploadProgress(0);
    
    try {
      const id = await addToQueue(capturedImage, rubric);
      setCapturedImage(null);
      setUploadProgress(100);
      router.push(`/processing/${id}`);
    } catch (error: any) {
      Alert.alert('Upload Failed', error.message);
    } finally {
      setUploading(false);
    }
  };

  const retake = () => {
    setCapturedImage(null);
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
            Inscrona needs camera access to photograph answer sheets.
          </Text>
          <Button title="Open Settings" onPress={() => require('expo-linking').openSettings()} />
        </Card>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Scan Answer Sheet</Text>
        <TouchableOpacity onPress={() => router.push('/settings')}>
          <Ionicons name="settings-outline" size={28} color={colors.gray} />
        </TouchableOpacity>
      </View>

      {/* Mode Selector */}
      <View style={styles.modeSelector}>
        <TouchableOpacity
          style={[
            styles.modeButton,
            mode === 'camera' && styles.modeButtonActive,
          ]}
          onPress={() => { setMode('camera'); setCapturedImage(null); }}
        >
          <Ionicons name="camera-outline" size={20} color={mode === 'camera' ? colors.primaryText : colors.gray} />
          <Text style={[
            styles.modeButtonText,
            mode === 'camera' && styles.modeButtonTextActive,
          ]}>Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[
            styles.modeButton,
            mode === 'gallery' && styles.modeButtonActive,
          ]}
          onPress={pickFromGallery}
        >
          <Ionicons name="images-outline" size={20} color={mode === 'gallery' ? colors.primaryText : colors.gray} />
          <Text style={[
            styles.modeButtonText,
            mode === 'gallery' && styles.modeButtonTextActive,
          ]}>Gallery</Text>
        </TouchableOpacity>
      </View>

      {/* Camera Preview / Captured Image */}
      <View style={styles.previewContainer}>
        {capturedImage ? (
          <View style={styles.capturedWrapper}>
            <Image source={{ uri: capturedImage }} style={styles.capturedImage} />
            <View style={styles.capturedActions}>
              <Button
                title="Retake"
                variant="secondary"
                onPress={retake}
                style={styles.actionButton}
              />
              <Button
                title="Use Photo"
                onPress={handleUpload}
                disabled={uploading}
                style={styles.actionButton}
              />
            </View>
          </View>
        ) : mode === 'camera' && hasPermission && (
          <CameraView
            ref={cameraRef}
            style={styles.cameraPreview}
            deviceType={CameraView.DeviceType.back}
            videoStabilizationMode={CameraView.VideoStabilizationMode.standard}
          />
        )}
      </View>

      {/* Rubric Input */}
      <Card variant="outlined" style={styles.rubricCard}>
        <Text style={styles.rubricLabel}>Grading Rubric</Text>
        <Input
          placeholder="Describe what to grade..."
          value={rubric}
          onChangeText={setRubric}
          multiline
          numberOfLines={3}
          style={{ marginTop: spacing.sm }}
        />
      </Card>

      {/* Upload Progress */}
      {uploading && (
        <Card variant="elevated" style={styles.progressCard}>
          <Progress
            progress={uploadProgress}
            stage="uploading"
            message="Preparing upload..."
            size="lg"
          />
        </Card>
      )}

      {/* Capture Button */}
      {!capturedImage && mode === 'camera' && hasPermission && (
        <TouchableOpacity
          style={styles.captureButton}
          onPress={takePicture}
          activeOpacity={0.8}
        >
          <View style={styles.captureInner} />
        </TouchableOpacity>
      )}

      {!capturedImage && mode === 'gallery' && (
        <View style={styles.galleryHint}>
          <Ionicons name="images-outline" size={48} color={colors.grayLight} />
          <Text style={styles.galleryHintText}>Tap "Gallery" to select an image</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  title: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  modeSelector: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
  },
  modeButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  modeButtonActive: {
    backgroundColor: colors.primary,
  },
  modeButtonText: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
  },
  modeButtonTextActive: {
    color: colors.primaryText,
  },
  previewContainer: {
    flex: 1,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: colors.surface,
  },
  cameraPreview: {
    flex: 1,
  },
  capturedWrapper: {
    flex: 1,
    position: 'relative',
  },
  capturedImage: {
    flex: 1,
    width: '100%',
  },
  capturedActions: {
    position: 'absolute',
    bottom: spacing.lg,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    gap: spacing.md,
  },
  actionButton: {
    flex: 1,
  },
  rubricCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.md,
  },
  rubricLabel: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.charcoal,
  },
  progressCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    padding: spacing.lg,
  },
  captureButton: {
    position: 'absolute',
    bottom: spacing.xl,
    alignSelf: 'center',
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    ...shadows.card,
  },
  captureInner: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 3,
    borderColor: colors.primaryText,
  },
  galleryHint: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
  },
  galleryHintText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
    textAlign: 'center',
  },
  errorCard: {
    alignItems: 'center',
    padding: spacing.xl,
    margin: spacing.lg,
  },
  errorTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
    marginBottom: spacing.sm,
    textAlign: 'center',
  },
  errorText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
});