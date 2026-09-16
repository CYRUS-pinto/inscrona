import { Pressable, Text, StyleSheet, View } from 'react-native';
import { colors, radius, spacing, typography, touchTarget, shadows } from '@/src/utils/theme';

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  fullWidth?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  style?: any;
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  fullWidth = true,
  leftIcon,
  rightIcon,
  style,
}: ButtonProps) {
  const isDisabled = disabled || loading;

  const variants = {
    primary: {
      bg: colors.primary,
      bgPressed: colors.primaryPressed,
      text: colors.primaryText,
      border: 'none',
    },
    secondary: {
      bg: 'transparent',
      bgPressed: colors.surfaceHover,
      text: colors.ink,
      border: colors.hairlineStrong,
    },
    ghost: {
      bg: 'transparent',
      bgPressed: colors.surfaceHover,
      text: colors.primary,
      border: 'transparent',
    },
    destructive: {
      bg: colors.errorBg,
      bgPressed: colors.error,
      text: colors.error,
      border: 'transparent',
    },
  };

  const sizes = {
    sm: {
      paddingV: spacing.xs,
      paddingH: spacing.md,
      fontSize: typography.fontSize.sm,
      height: 36,
      minHeight: 36,
    },
    md: {
      paddingV: spacing.sm,
      paddingH: spacing.lg,
      fontSize: typography.fontSize.base,
      height: 44,
      minHeight: touchTarget.minHeight,
    },
    lg: {
      paddingV: spacing.md,
      paddingH: spacing.xl,
      fontSize: typography.fontSize.lg,
      height: 52,
      minHeight: 52,
    },
  };

  const v = variants[variant];
  const s = sizes[size];

  return (
    <Pressable
      onPress={isDisabled ? undefined : onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.container,
        fullWidth && styles.fullWidth,
        {
          backgroundColor: pressed ? v.bgPressed : v.bg,
          borderColor: v.border,
          borderWidth: v.border === 'transparent' ? 0 : 1,
          borderRadius: radius.md,
          height: s.height,
          minHeight: s.minHeight,
          paddingVertical: s.paddingV,
          paddingHorizontal: s.paddingH,
          opacity: isDisabled ? 0.5 : 1,
        },
        style,
      ]}
      android_ripple={{ color: colors.grayLight, borderless: false, radius: radius.md }}
    >
      <View style={styles.content}>
        {loading ? (
          <Text style={[styles.spinner, { color: v.text }]}>⏳</Text>
        ) : (
          <>
            {leftIcon && <View style={styles.icon}>{leftIcon}</View>}
            <Text
              style={[
                styles.title,
                { color: v.text, fontSize: s.fontSize, fontFamily: typography.fontFamily.medium },
              ]}
            >
              {title}
            </Text>
            {rightIcon && <View style={styles.icon}>{rightIcon}</View>}
          </>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  fullWidth: { width: '100%' },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  title: {
    textAlign: 'center',
  },
  icon: {
    width: 20,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  spinner: {
    fontSize: 16,
  },
});