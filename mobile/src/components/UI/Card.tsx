import { View, ViewStyle, StyleSheet } from 'react-native';
import { colors, radius, spacing, shadows } from '@/src/utils/theme';

interface CardProps {
  children: React.ReactNode;
  style?: ViewStyle;
  variant?: 'default' | 'elevated' | 'outlined' | 'tinted';
  tintColor?: string;
  padding?: keyof typeof spacing;
  onPress?: () => void;
}

export function Card({
  children,
  style,
  variant = 'default',
  tintColor,
  padding = 'lg',
  onPress,
}: CardProps) {
  const variants = {
    default: {
      backgroundColor: colors.canvas,
      borderWidth: 1,
      borderColor: colors.hairline,
      ...shadows.card,
    },
    elevated: {
      backgroundColor: colors.canvas,
      borderWidth: 0,
      ...shadows.card,
    },
    outlined: {
      backgroundColor: colors.canvas,
      borderWidth: 1,
      borderColor: colors.hairlineStrong,
      ...shadows.cardSmall,
    },
    tinted: {
      backgroundColor: tintColor || colors.surface,
      borderWidth: 0,
      ...shadows.cardSmall,
    },
  };

  const v = variants[variant];
  const p = spacing[padding];

  const Container = onPress ? View : View;

  return (
    <View
      style={[
        styles.container,
        v,
        { borderRadius: radius.lg, padding: p },
        style,
      ]}
      {...(onPress ? { onTouchStart: onPress, pointerEvents: 'box-none' as any } : {})}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {},
});