import { View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Alert } from 'react-native';
import { Card } from '@/src/components/UI/Card';
import { Badge } from '@/src/components/UI/Badge';
import { Button } from '@/src/components/UI/Button';
import { Progress } from '@/src/components/UI/Progress';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter } from 'expo-router';
import { useEffect, useState, useCallback } from 'react';
import { api } from '@/src/api/client';
import { GradeResult, PendingUpload } from '@/src/types';
import { Ionicons } from '@expo/vector-icons';
import { useUploadStore } from '@/src/store/uploadStore';
import { useAuthStore } from '@/src/store/authStore';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';

export default function HistoryScreen() {
  const router = useRouter();
  const { backendUrl } = useAuthStore();
  const { pendingUploads, completedResults, processQueue, removeFromQueue, retryUpload, clearCompleted } = useUploadStore();
  const [results, setResults] = useState<GradeResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showExport, setShowExport] = useState(false);

  const fetchResults = useCallback(async () => {
    try {
      const data = await api.getResults();
      setResults(data);
    } catch (error) {
      console.warn('Failed to fetch results:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchResults();
    processQueue();
    const interval = setInterval(processQueue, 30000);
    return () => clearInterval(interval);
  }, [fetchResults, processQueue]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchResults();
  };

  const exportAll = async () => {
    try {
      const csv = await api.exportCsv();
      const uri = FileSystem.documentDirectory + 'inscrona_grades.csv';
      await FileSystem.writeAsStringAsync(uri, csv);
      await Sharing.shareAsync(uri, { mimeType: 'text/csv', dialogTitle: 'Export All Grades' });
      setShowExport(false);
    } catch (error) {
      Alert.alert('Export Failed', 'Could not export CSV');
    }
  };

  const getConfidenceVariant = (confidence: number): 'success' | 'warning' | 'error' | 'neutral' => {
    if (confidence >= 0.8) return 'success';
    if (confidence >= 0.6) return 'warning';
    return 'error';
  };

  const pendingCount = pendingUploads.filter(u => u.status !== 'completed').length;

  if (loading && results.length === 0) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} colors={[colors.primary]} />
      }
      contentContainerStyle={styles.content}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.title}>History</Text>
          <Text style={styles.subtitle}>
            {results.length} graded • {pendingCount > 0 && `${pendingCount} pending`}
          </Text>
        </View>
        <View style={styles.headerActions}>
          {(results.length > 0 || pendingCount > 0) && (
            <Button
              title="Export CSV"
              variant="secondary"
              size="sm"
              leftIcon={<Ionicons name="download-outline" size={16} />}
              onPress={() => setShowExport(true)}
            />
          )}
        </View>
      </View>

      {/* Pending Uploads */}
      {pendingCount > 0 && (
        <Card variant="elevated" style={styles.pendingCard}>
          <View style={styles.pendingHeader}>
            <Text style={styles.pendingTitle}>Pending Uploads</Text>
            <Badge variant="warning" size="sm">{pendingCount}</Badge>
          </View>
          <View style={styles.pendingList}>
            {pendingUploads
              .filter(u => u.status !== 'completed')
              .map((upload) => (
                <View key={upload.id} style={styles.pendingItem}>
                  <View style={styles.pendingInfo}>
                    <Text style={styles.pendingStatus}>
                      {upload.status === 'uploading' ? 'Uploading...' : 
                       upload.status === 'failed' ? `Failed (${upload.retry_count}/${3})` : 'Queued'}
                    </Text>
                    <Text style={styles.pendingTime}>
                      {new Date(upload.created_at).toLocaleTimeString()}
                    </Text>
                  </View>
                  <View style={styles.pendingActions}>
                    {upload.status === 'failed' && upload.retry_count < 3 && (
                      <Button
                        title="Retry"
                        variant="primary"
                        size="sm"
                        onPress={() => retryUpload(upload.id)}
                      />
                    )}
                    <Button
                      title="Remove"
                      variant="ghost"
                      size="sm"
                      onPress={() => removeFromQueue(upload.id)}
                    />
                  </View>
                </View>
              ))}
          </View>
        </Card>
      )}

      {/* Completed Results */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Completed Grades</Text>
        {results.length > 0 && (
          <Button
            title="Clear"
            variant="ghost"
            size="sm"
            onPress={clearCompleted}
          />
        )}
      </View>

      {results.length === 0 && pendingCount === 0 ? (
        <Card variant="outlined" style={styles.emptyCard}>
          <Ionicons name="document-text-outline" size={48} color={colors.grayLight} />
          <Text style={styles.emptyTitle}>No grades yet</Text>
          <Text style={styles.emptyText}>
            Scan your first answer sheet to get started
          </Text>
          <Button
            title="Start Scanning"
            variant="primary"
            onPress={() => router.push('/(tabs)/camera')}
            style={styles.emptyButton}
          />
        </Card>
      ) : (
        <View style={styles.resultsList}>
          {results.map((result) => (
            <TouchableOpacity
              key={result.id}
              style={styles.resultCard}
              onPress={() => router.push(`/result/${result.id}`)}
              activeOpacity={0.8}
            >
              <View style={styles.resultLeft}>
                <View style={[
                  styles.resultBadge,
                  result.confidence >= 0.8 && styles.badgeSuccess,
                  result.confidence >= 0.6 && result.confidence < 0.8 && styles.badgeWarning,
                  result.confidence < 0.6 && styles.badgeError,
                ]}>
                  <Text style={styles.resultMarks}>
                    {result.marks}/10
                  </Text>
                </View>
              </View>
              <View style={styles.resultCenter}>
                <Text style={styles.resultFeedback} numberOfLines={2}>
                  {result.feedback}
                </Text>
                <View style={styles.resultMeta}>
                  <Text style={styles.resultTime}>
                    {new Date(result.created_at).toLocaleDateString()} • {Math.round(result.processing_time_ms / 1000)}s
                  </Text>
                  <Badge variant={getConfidenceVariant(result.confidence)} size="sm">
                    {Math.round(result.confidence * 100)}%
                  </Badge>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.grayLight} />
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Export Modal */}
      {showExport && (
        <View style={styles.modalOverlay} onTouchStart={() => setShowExport(false)}>
          <Card variant="elevated" style={styles.modalCard}>
            <Text style={styles.modalTitle}>Export Grades</Text>
            <Text style={styles.modalText}>
              Export all {results.length} completed grades as a CSV file
            </Text>
            <View style={styles.modalActions}>
              <Button title="Cancel" variant="secondary" onPress={() => setShowExport(false)} />
              <Button title="Export CSV" variant="primary" onPress={exportAll} />
            </View>
          </Card>
        </View>
      )}
    </ScrollView>
  );
}

import { ActivityIndicator, ViewStateCallback } from 'react-native';
import { useState } from 'react';

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
  headerLeft: { flex: 1 },
  headerActions: { flexDirection: 'row', gap: spacing.sm },
  title: {
    fontSize: typography.fontSize['3xl'],
    fontFamily: typography.fontFamily.bold,
    color: colors.navy,
  },
  subtitle: {
    fontSize: typography.fontSize.sm,
    color: colors.gray,
    marginTop: 2,
  },
  pendingCard: {
    gap: spacing.md,
  },
  pendingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  pendingTitle: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  pendingList: {
    gap: spacing.md,
  },
  pendingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
  },
  pendingInfo: { gap: 2 },
  pendingStatus: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  pendingTime: {
    fontSize: typography.fontSize.xs,
    color: colors.gray,
  },
  pendingActions: { flexDirection: 'row', gap: spacing.sm },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: typography.fontSize.base,
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
  },
  emptyCard: {
    alignItems: 'center',
    padding: spacing.xxl,
    gap: spacing.md,
  },
  emptyTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  emptyText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
    textAlign: 'center',
  },
  emptyButton: { marginTop: spacing.md, width: '80%' },
  resultsList: { gap: spacing.md },
  resultCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    backgroundColor: colors.canvas,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.lg,
    gap: spacing.md,
    ...shadows.cardSmall,
  },
  resultLeft: { width: 60 },
  resultBadge: {
    width: 56,
    height: 56,
    borderRadius: radius.full,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  badgeSuccess: { backgroundColor: colors.success },
  badgeWarning: { backgroundColor: colors.warning },
  badgeError: { backgroundColor: colors.error },
  resultMarks: {
    fontSize: typography.fontSize.lg,
    fontFamily: typography.fontFamily.monoMedium,
    color: colors.primaryText,
  },
  resultCenter: { flex: 1, gap: spacing.xs },
  resultFeedback: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.regular,
    color: colors.ink,
  },
  resultMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.xs,
  },
  resultTime: {
    fontSize: typography.fontSize.xs,
    color: colors.gray,
  },
  modalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 400,
    gap: spacing.md,
  },
  modalTitle: {
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
  },
  modalText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
  },
  modalActions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.md,
  },
});