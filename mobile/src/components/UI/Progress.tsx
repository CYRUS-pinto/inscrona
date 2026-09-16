import { View, Text, StyleSheet, Animated, Easing } from 'react-native';
import { colors, radius, spacing, typography, animation } from '@/src/utils/theme';

interface ProgressProps {
  progress: number; // 0-100
  stage: 'uploading' | 'ocr' | 'grading' | 'saving' | 'completed' | 'error';
  message?: string;
  showPercentage?: boolean;
  size?: 'sm' | 'md' | 'lg';
  animated?: boolean;
}

const stageLabels = {
  uploading: 'Uploading image...',
  ocr: 'Reading text with GLM-OCR...',
  grading: 'Grading with Llama 3.2...',
  saving: 'Saving results...',
  completed: 'Complete!',
  error: 'Error occurred',
};

const stageIcons = {
  uploading: '📤',
  ocr: '🔍',
  grading: '🧠',
  saving: '💾',
  completed: '✅',
  error: '❌',
};

export function Progress({
  progress,
  stage,
  message,
  showPercentage = true,
  size = 'md',
  animated = true,
}: ProgressProps) {
  const [animProgress] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (animated) {
      Animated.timing(animProgress, {
        toValue: progress / 100,
        duration: animation.normal,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: false,
      }).start();
    } else {
      animProgress.setValue(progress / 100);
    }
  }, [progress, animated, animProgress]);

  const sizes = {
    sm: { height: 4, fontSize: typography.fontSize.xs, gap: spacing.xs },
    md: { height: 8, fontSize: typography.fontSize.sm, gap: spacing.sm },
    lg: { height: 12, fontSize: typography.fontSize.base, gap: spacing.md },
  };

  const s = sizes[size];
  const label = message || stageLabels[stage];
  const icon = stageIcons[stage];

  const bgColor = stage === 'error' ? colors.error : 
                  stage === 'completed' ? colors.success : 
                  colors.primary;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { gap: s.gap }]}>
        <Text style={[styles.icon, { fontSize: s.fontSize + 4 }]}>{icon}</Text>
        <Text style={[styles.label, { fontSize: s.fontSize }]}>{label}</Text>
        {showPercentage && (
          <Text style={[styles.percentage, { fontSize: s.fontSize }]}>{Math.round(progress)}%</Text>
        )}
      </View>
      <View style={[styles.track, { height: s.height }]}>
        <Animated.View
          style={[
            styles.fill,
            { backgroundColor: bgColor, borderRadius: radius.full },
            { width: `${animProgress.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] })}` },
          ]}
        />
      </View>
    </View>
  );
}

import { useState, useEffect } from 'react';

const styles = StyleSheet.create({
  container: {
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  icon: {},
  label: {
    fontFamily: typography.fontFamily.medium,
    color: colors.ink,
    flex: 1,
  },
  percentage: {
    fontFamily: typography.fontFamily.monoMedium,
    color: colors.primary,
  },
  track: {
    backgroundColor: colors.grayLighter,
    borderRadius: radius.full,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: radius.full,
  },
});