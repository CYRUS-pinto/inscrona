import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { Progress } from '@/src/components/UI/Progress';
import { Card } from '@/src/components/UI/Card';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useEffect, useState, useRef } from 'react';
import { api } from '@/src/api/client';
import { UploadProgress, GradeResult } from '@/src/types';

export default function ProcessingScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [progress, setProgress] = useState<UploadProgress>({
    stage: 'uploading',
    progress: 0,
    message: 'Starting...',
  });
  const [result, setResult] = useState<GradeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    if (!id) return;

    // Register for progress updates
    cleanupRef.current = api.connectProgress(id, (p) => {
      setProgress(p);
      if (p.result) {
        setResult(p.result);
      }
      if (p.error) {
        setError(p.error);
      }
    });

    // Timeout fallback
    timeoutRef.current = setTimeout(() => {
      if (!result && !error) {
        setError('Processing timed out. Check your connection and try again.');
      }
    }, 300000); // 5 min timeout

    return () => {
      cleanupRef.current?.();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [id, result, error]);

  useEffect(() => {
    if (result) {
      setTimeout(() => {
        router.push(`/result/${id}`);
      }, 1500);
    }
  }, [result, id, router]);

  const stageOrder = ['uploading', 'ocr', 'grading', 'saving', 'completed'];
  const currentStageIndex = stageOrder.indexOf(progress.stage);
  const overallProgress = currentStageIndex >= 0 
    ? ((currentStageIndex / (stageOrder.length - 1)) * 100) + (progress.progress / 100) * (100 / (stageOrder.length - 1))
    : 0;

  if (error) {
    return (
      <View style={styles.container}>
        <Card variant="elevated" style={styles.errorCard}>
          <Text style={styles.errorIcon}>❌</Text>
          <Text style={styles.errorTitle}>Processing Failed</Text>
          <Text style={styles.errorText}>{error}</Text>
          <View style={styles.errorActions}>
            <Button title="Retry" variant="primary" onPress={() => router.back()} />
            <Button title="Go Home" variant="secondary" onPress={() => router.replace('/(tabs)/camera')} />
          </View>
        </Card>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Processing</Text>
      </View>

      <Card variant="elevated" style={styles.mainCard}>
        <View style={styles.progressSection}>
          <Progress
            progress={Math.min(overallProgress, 100)}
            stage={progress.stage}
            message={progress.message}
            size="lg"
          />
        </View>

        <View style={styles.stagesContainer}>
          {stageOrder.map((stage, index) => (
            <View key={stage} style={styles.stageRow}>
              <View style={[
                styles.stageDot,
                index < currentStageIndex && styles.stageDotCompleted,
                index === currentStageIndex && styles.stageDotActive,
              ]}>
                {index < currentStageIndex && <Text style={styles.stageCheck}>✓</Text>}
              </View>
              <View style={styles.stageContent}>
                <Text style={[
                  styles.stageLabel,
                  index < currentStageIndex && styles.stageCompleted,
                  index === currentStageIndex && styles.stageActive,
                ]}>
                  {stageLabels[stage]}
                </Text>
                <Text style={[
                  styles.stageStatus,
                  index < currentStageIndex && styles.stageStatusCompleted,
                  index === currentStageIndex && styles.stageStatusActive,
                ]}>
                  {index < currentStageIndex ? 'Completed' : 
                   index === currentStageIndex ? 'In progress' : 'Pending'}
                </Text>
              </View>
            </View>
          ))}
        </View>

        {progress.stage === 'completed' && (
          <View style={styles.completeSection}>
            <Text style={styles.completeText}>✅ Grading complete! Redirecting...</Text>
          </View>
        )}
      </Card>
    </View>
  );
}

const stageLabels: Record<string, string> = {
  uploading: 'Uploading image',
  ocr: 'Reading text with GLM-OCR',
  grading: 'Grading with Llama 3.2',
  saving: 'Saving results',
  completed: 'Complete',
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
  },
  header: {
    marginBottom: spacing.xl,
  },
  title: {
    fontSize: typography.fontSize['3xl'],
    fontFamily: typography.fontFamily.bold,
    color: colors.navy,
  },
  mainCard: {
    gap: spacing.xl,
  },
  progressSection: {
    paddingBottom: spacing.md,
  },
  stagesContainer: {
    gap: spacing.lg,
  },
  stageRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  stageDot: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.grayLight,
    backgroundColor: colors.canvas,
    justifyContent: 'center',
    alignItems: 'center',
    flexShrink: 0,
    marginTop: 2,
  },
  stageDotCompleted: {
    backgroundColor: colors.success,
    borderColor: colors.success,
  },
  stageDotActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  stageCheck: {
    fontSize: 12,
    color: colors.primaryText,
    fontWeight: 'bold',
  },
  stageContent: {
    flex: 1,
    gap: 2,
  },
  stageLabel: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  stageCompleted: {
    color: colors.success,
  },
  stageActive: {
    color: colors.primary,
  },
  stageStatus: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
  },
  stageStatusCompleted: {
    color: colors.success,
  },
  stageStatusActive: {
    color: colors.primary,
  },
  completeSection: {
    paddingTop: spacing.md,
    alignItems: 'center',
  },
  completeText: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.medium,
    color: colors.success,
  },
  errorCard: {
    alignItems: 'center',
    padding: spacing.xxl,
    margin: spacing.lg,
    gap: spacing.lg,
  },
  errorIcon: {
    fontSize: 48,
  },
  errorTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  errorText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
    textAlign: 'center',
  },
  errorActions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.md,
  },
});