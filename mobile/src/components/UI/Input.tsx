import { TextInput, View, Text, StyleSheet } from 'react-native';
import { colors, radius, spacing, typography } from '@/src/utils/theme';

interface InputProps {
  label?: string;
  placeholder?: string;
  value: string;
  onChangeText: (text: string) => void;
  error?: string;
  helperText?: string;
  secureTextEntry?: boolean;
  keyboardType?: 'default' | 'email-address' | 'numeric' | 'phone-pad';
  disabled?: boolean;
  multiline?: boolean;
  numberOfLines?: number;
  style?: any;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  onBlur?: () => void;
}

export function Input({
  label,
  placeholder,
  value,
  onChangeText,
  error,
  helperText,
  secureTextEntry = false,
  keyboardType = 'default',
  disabled = false,
  multiline = false,
  numberOfLines,
  style,
  leftIcon,
  rightIcon,
  onBlur,
}: InputProps) {
  const hasError = !!error;

  return (
    <View style={[styles.container, style]}>
      {label && (
        <Text style={styles.label}>{label}</Text>
      )}
      <View style={styles.inputWrapper}>
        {leftIcon && <View style={styles.icon}>{leftIcon}</View>}
        <TextInput
          style={[
            styles.input,
            {
              borderColor: hasError ? colors.error : colors.hairlineStrong,
              backgroundColor: disabled ? colors.surface : colors.canvas,
              color: colors.ink,
              fontSize: typography.fontSize.base,
              fontFamily: typography.fontFamily.regular,
              borderRadius: radius.md,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.sm,
              minHeight: 44,
              borderWidth: 1,
            },
            multiline && { paddingTop: spacing.md, paddingBottom: spacing.md },
          ]}
          placeholder={placeholder}
          placeholderTextColor={colors.gray}
          value={value}
          onChangeText={onChangeText}
          onBlur={onBlur}
          secureTextEntry={secureTextEntry}
          keyboardType={keyboardType}
          disabled={disabled}
          multiline={multiline}
          numberOfLines={numberOfLines}
          autoCapitalize="none"
          autoCorrect={false}
          textContentType={keyboardType === 'email-address' ? 'email' : undefined}
        />
        {rightIcon && <View style={styles.icon}>{rightIcon}</View>}
      </View>
      {hasError && <Text style={styles.errorText}>{error}</Text>}
      {!hasError && helperText && <Text style={styles.helperText}>{helperText}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.xs,
  },
  label: {
    fontSize: typography.fontSize.sm,
    fontFamily: typography.fontFamily.medium,
    color: colors.charcoal,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: multiline ? 'flex-start' : 'center',
    gap: spacing.sm,
  },
  input: {
    flex: 1,
  },
  icon: {
    width: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    fontSize: typography.fontSize.xs,
    color: colors.error,
  },
  helperText: {
    fontSize: typography.fontSize.xs,
    color: colors.gray,
  },
});