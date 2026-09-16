export const colors = {
  // Notion/Stitch design tokens
  primary: '#5645d4',
  primaryPressed: '#4534b3',
  primaryText: '#ffffff',
  
  navy: '#0a1530',
  navyLight: '#070f24',
  
  canvas: '#ffffff',
  surface: '#f6f5f4',
  surfaceHover: '#ebe9e6',
  
  ink: '#1a1a1a',
  charcoal: '#37352f',
  gray: '#787774',
  grayLight: '#c8c4be',
  grayLighter: '#e5e3df',
  
  hairline: '#e5e3df',
  hairlineStrong: '#c8c4be',
  
  // Semantic colors
  success: '#1aae39',
  successBg: '#d9f3e1',
  successText: '#1aae39',
  
  warning: '#dd5b00',
  warningBg: '#ffe8d4',
  warningText: '#793400',
  
  error: '#e03131',
  errorBg: '#ffebeb',
  errorText: '#e03131',
  
  // Dark mode
  dark: {
    canvas: '#0a0a0a',
    surface: '#131313',
    surfaceHover: '#1c1c1c',
    ink: '#ffffff',
    charcoal: '#d0cfce',
    gray: '#9b9a97',
    grayLight: '#5c5b59',
    hairline: '#2d2d2d',
    hairlineStrong: '#3d3d3d',
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const radius = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  full: 9999,
};

export const shadows = {
  card: {
    shadowColor: '#0f0f0f',
    shadowOffset: { width: 0, height: 24 },
    shadowOpacity: 0.2,
    shadowRadius: 48,
    elevation: 8,
  },
  cardSmall: {
    shadowColor: '#0f0f0f',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  input: {
    shadowColor: '#0f0f0f',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0,
    shadowRadius: 0,
    elevation: 0,
  },
};

export const typography = {
  fontFamily: {
    regular: 'Inter_400Regular',
    medium: 'Inter_500Medium',
    semiBold: 'Inter_600SemiBold',
    bold: 'Inter_700Bold',
    mono: 'JetBrainsMono_400Regular',
    monoMedium: 'JetBrainsMono_500Medium',
  },
  fontSize: {
    xs: 12,
    sm: 13,
    base: 14,
    lg: 15,
    xl: 16,
    '2xl': 18,
    '3xl': 22,
    '4xl': 28,
  },
  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
};

export const breakpoints = {
  sm: 375,
  md: 768,
  lg: 1024,
  xl: 1440,
};

export const animation = {
  fast: 150,
  normal: 200,
  slow: 300,
  spring: {
    damping: 15,
    stiffness: 150,
  },
};

export const touchTarget = {
  minHeight: 44,
  minWidth: 44,
};

export const zIndex = {
  base: 0,
  dropdown: 10,
  sticky: 20,
  modal: 40,
  popover: 50,
  toast: 100,
  tooltip: 1000,
};