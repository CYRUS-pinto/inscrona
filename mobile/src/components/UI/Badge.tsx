import { View, Text, StyleSheet } from 'react-native';
import { colors, radius, spacing, typography } from '@/src/utils/theme';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'error' | 'neutral' | 'primary';
  size?: 'sm' | 'md' | 'lg';
  style?: any;
}

export function Badge({
  children,
  variant = 'neutral',
  size = 'md',
  style,
}: BadgeProps) {
  const variants = {
    success: { bg: colors.successBg, text: colors.successText },
    warning: { bg: colors.warningBg, text: colors.warningText },
    error: { bg: colors.errorBg, text: colors.errorText },
    neutral: { bg: colors.grayLighter, text: colors.charcoal },
    primary: { bg: colors.primary, text: colors.primaryText },
  };

  const sizes = {
    sm: { paddingH: spacing.sm, paddingV: 2, fontSize: typography.fontSize.xs, height: 20 },
    md: { paddingH: spacing.md, paddingV: 4, fontSize: typography.fontSize.sm, height: 24 },
    lg: { paddingH: spacing.lg, paddingV: 6, fontSize: typography.fontSize.base, height: 32 },
  };

  const v = variants[variant];
  const s = sizes[size];

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: v.bg,
          borderRadius: radius.full,
          paddingHorizontal: s.paddingH,
          paddingVertical: s.paddingV,
          minHeight: s.height,
        },
        style,
      ]}
    >
      <Text
        style={[
          styles.text,
          { color: v.text, fontSize: s.fontSize, fontFamily: typography.fontFamily.medium },
        ]}
      >
        {children}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
  },
  text: {},
});