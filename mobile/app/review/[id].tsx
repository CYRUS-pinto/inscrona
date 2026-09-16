import { View, Text, StyleSheet, Image, TouchableOpacity, Alert } from 'react-native';
import { Button } from '@/src/components/UI/Button';
import { Card } from '@/src/components/UI/Card';
import { Input } from '@/src/components/UI/Input';
import { colors, spacing, radius, typography, shadows } from '@/src/utils/theme';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useState, useEffect } from 'react';
import { api } from '@/src/api/client';
import { GradeResult } from '@/src/types';
import { Ionicons } from '@expo/vector-icons';

export default function ReviewScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [rubric, setRubric] = useState('Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity.');
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (id) {
      // Load image from uploads directory if exists
      setImageUri(`file://${id}.jpg`);
    }
  }, [id]);

  const handleConfirm = async () => {
    if (!imageUri) return;
    setUploading(true);
    try {
      const result = await api.gradeImage(imageUri, rubric);
      router.push(`/result/${result.id}`);
    } catch (error: any) {
      Alert.alert('Upload Failed', error.message);
    } finally {
      setUploading(false);
    }
  };

  const retake = () => {
    router.back();
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={retake}>
          <Ionicons name="chevron-back" size={28} color={colors.gray} />
        </TouchableOpacity>
        <Text style={styles.title}>Review & Confirm</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Image Preview */}
        <Card variant="elevated" style={styles.imageCard}>
          {imageUri ? (
            <Image source={{ uri: imageUri }} style={styles.previewImage} resizeMode="contain" />
          ) : (
            <View style={styles.noImage}>
              <Ionicons name="image-outline" size={48} color={colors.grayLight} />
              <Text style={styles.noImageText}>No image loaded</Text>
            </View>
          )}
        </Card>

        {/* Rubric Input */}
        <Card variant="outlined" style={styles.rubricCard}>
          <Text style={styles.rubricLabel}>Grading Rubric</Text>
          <Input
            placeholder="Describe what to grade..."
            value={rubric}
            onChangeText={setRubric}
            multiline
            numberOfLines={4}
            style={{ marginTop: spacing.sm }}
          />
        </Card>

        {/* Actions */}
        <View style={styles.actions}>
          <Button
            title="Retake Photo"
            variant="secondary"
            leftIcon={<Ionicons name="camera-outline" size={20} />}
            onPress={retake}
            fullWidth
          />
          <Button
            title={uploading ? 'Submitting...' : 'Submit for Grading'}
            variant="primary"
            leftIcon={<Ionicons name="send-outline" size={20} />}
            onPress={handleConfirm}
            disabled={uploading || !imageUri}
            fullWidth
          />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
  },
  title: {
    flex: 1,
    fontSize: typography.fontSize.xl,
    fontFamily: typography.fontFamily.semiBold,
    color: colors.ink,
    textAlign: 'center',
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
    gap: spacing.lg,
  },
  imageCard: {
    overflow: 'hidden',
  },
  previewImage: {
    width: '100%',
    aspectRatio: 1,
  },
  noImage: {
    alignItems: 'center',
    padding: spacing.xxxl,
    gap: spacing.md,
  },
  noImageText: {
    fontSize: typography.fontSize.base,
    color: colors.gray,
  },
  rubricCard: {
    gap: spacing.md,
  },
  rubricLabel: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.charcoal,
  },
  actions: {
    gap: spacing.md,
  },
});