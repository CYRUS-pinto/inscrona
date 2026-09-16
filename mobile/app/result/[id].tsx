import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert } from 'react-native';
import { Card } from '@/src/components/UI/Card';
import { Badge } from '@/src/components/UI/Badge';
import { Button } from '@/src/components/UI/Button';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { api } from '@/src/api/client';
import { GradeResult } from '@/src/types';
import { Ionicons } from '@expo/vector-icons';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';

export default function ResultScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [result, setResult] = useState<GradeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [ocrExpanded, setOcrExpanded] = useState(false);

  useEffect(() => {
    loadResult();
  }, [id]);

  const loadResult = async () => {
    if (!id) return;
    try {
      const data = await api.getResult(id);
      setResult(data);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to load result');
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return { variant: 'success' as const, label: 'Auto-Accept' };
    if (confidence >= 0.6) return { variant: 'warning' as const, label: 'Review Needed' };
    return { variant: 'error' as const, label: 'Manual Check' };
  };

  const confidenceInfo = result ? getConfidenceColor(result.confidence) : { variant: 'neutral' as const, label: '—' };

  const shareResult = async () => {
    if (!result) return;
    const text = `Inscrona Grade Report\n\nMarks: ${result.marks}/10\nConfidence: ${Math.round(result.confidence * 100)}% (${confidenceInfo.label})\nFeedback: ${result.feedback}\n\nOCR Transcript:\n${result.ocr_text}`;
    await Sharing.shareAsync(text, { mimeType: 'text/plain', dialogTitle: 'Share Grade' });
  };

  const exportCsv = async () => {
    try {
      const csv = await api.exportCsv();
      const uri = FileSystem.documentDirectory + 'inscrona_grades.csv';
      await FileSystem.writeAsStringAsync(uri, csv);
      await Sharing.shareAsync(uri, { mimeType: 'text/csv', dialogTitle: 'Export Grades' });
    } catch (error) {
      Alert.alert('Export Failed', 'Could not export CSV');
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!result) {
    return (
      <View style={styles.container}>
        <Card variant="elevated" style={styles.errorCard}>
          <Text style={styles.errorTitle}>Result Not Found</Text>
          <Button title="Back to History" onPress={() => router.back()} />
        </Card>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={28} color={colors.gray} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Grade Result</Text>
        <TouchableOpacity onPress={shareResult}>
          <Ionicons name="share-outline" size={28} color={colors.primary} />
        </TouchableOpacity>
      </View>

      {/* Main Result Card */}
      <Card variant="elevated" style={styles.resultCard}>
        <View style={styles.resultHeader}>
          <View style={styles.marksContainer}>
            <Text style={styles.marksLabel}>MARKS</Text>
            <Text style={styles.marksValue}>{result.marks} / 10</Text>
          </View>
          <Badge variant={confidenceInfo.variant} size="lg">
            {confidenceInfo.label}
          </Badge>
        </View>

        <View style={styles.divider} />

        <View style={styles.feedbackSection}>
          <Text style={styles.sectionLabel}>FEEDBACK</Text>
          <Text style={styles.feedbackText}>{result.feedback}</Text>
        </View>
      </Card>

      {/* OCR Transcript Card */}
      <Card variant="outlined" style={styles.ocrCard}>
        <TouchableOpacity style={styles.ocrHeader} onPress={() => setOcrExpanded(!ocrExpanded)}>
          <View style={styles.ocrHeaderLeft}>
            <Ionicons name="document-text-outline" size={20} color={colors.primary} />
            <Text style={styles.ocrHeaderTitle}>OCR Transcript</Text>
          </View>
          <Ionicons name={ocrExpanded ? 'chevron-up' : 'chevron-down'} size={24} color={colors.gray} />
        </TouchableOpacity>

        {ocrExpanded && (
          <View style={styles.ocrContent}>
            <Text style={styles.ocrText}>{result.ocr_text || 'No transcript available'}</Text>
          </View>
        )}
      </Card>

      {/* Metadata */}
      <Card variant="outlined" style={styles.metaCard}>
        <Text style={styles.sectionLabel}>DETAILS</Text>
        <View style={styles.metaGrid}>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Processed</Text>
            <Text style={styles.metaValue}>
              {new Date(result.created_at).toLocaleString()}
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Processing Time</Text>
            <Text style={styles.metaValue}>
              {Math.round(result.processing_time_ms / 1000)}s
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Text style={styles.metaLabel}>Rubric</Text>
            <Text style={styles.metaValue} numberOfLines={2}>
              {result.rubric}
            </Text>
          </View>
        </View>
      </Card>

      {/* Actions */}
      <View style={styles.actions}>
        <Button
          title="New Scan"
          variant="primary"
          leftIcon={<Ionicons name="camera-outline" size={20} />}
          onPress={() => router.replace('/(tabs)/camera')}
          fullWidth
        />
        <Button
          title="View History"
          variant="secondary"
          leftIcon={<Ionicons name="time-outline" size={20} />}
          onPress={() => router.replace('/(tabs)/history')}
          fullWidth
        />
      </View>
    </ScrollView>
  );
}

import { ActivityIndicator } from 'react-native';

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.lg,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  headerTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
    flex: 1,
    textAlign: 'center',
    marginLeft: -spacing.md,
  },
  resultCard: {
    gap: spacing.lg,
  },
  resultHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  marksContainer: {
    alignItems: 'center',
  },
  marksLabel: {
    fontSize: typography.fontSize.xs,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  marksValue: {
    fontSize: typography.fontSize['4xl'],
    fontFamily: typography.fontFamily.monoMedium,
    color: colors.ink,
    lineHeight: typography.fontSize['4xl'] * 1.1,
  },
  divider: {
    height: 1,
    backgroundColor: colors.hairline,
    marginVertical: spacing.md,
  },
  feedbackSection: {
    gap: spacing.xs,
  },
  sectionLabel: {
    fontSize: typography.fontSize.xs,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  feedbackText: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.regular,
    color: colors.ink,
    lineHeight: typography.fontSize.base * 1.6,
  },
  ocrCard: {
    overflow: 'hidden',
  },
  ocrHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
  },
  ocrHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  ocrHeaderTitle: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  ocrContent: {
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    marginHorizontal: -spacing.lg,
    marginBottom: -spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },
  ocrText: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.mono,
    color: colors.charcoal,
    lineHeight: typography.fontSize.sm * 1.7,
  },
  metaCard: {
    gap: spacing.md,
  },
  metaGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.lg,
  },
  metaItem: {
    flex: 1,
    minWidth: 120,
    gap: spacing.xs,
  },
  metaLabel: {
    fontSize: typography.fontSize.xs,
    fontFamily: typography.fontFamily.medium,
    color: colors.gray,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  metaValue: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.regular,
    color: colors.ink,
  },
  actions: {
    gap: spacing.md,
    marginTop: spacing.md,
  },
  errorCard: {
    alignItems: 'center',
    padding: spacing.xxl,
    margin: spacing.lg,
    gap: spacing.lg,
  },
  errorTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
    textAlign: 'center',
  },
});