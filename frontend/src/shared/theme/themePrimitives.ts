import { createTheme, alpha } from '@mui/material/styles';
import type { Shadows } from "@mui/material/styles";

declare module '@mui/material/Paper' {
  interface PaperPropsVariantOverrides {
    highlighted: true;
  }
}
declare module '@mui/material/styles' {
  interface ColorRange {
    50: string;
    100: string;
    200: string;
    300: string;
    400: string;
    500: string;
    600: string;
    700: string;
    800: string;
    900: string;
  }

  // MUI module augmentation: ColorRange is merged into PaletteColor.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface PaletteColor extends ColorRange {}

  interface Palette {
    baseShadow: string;
  }
}

const defaultTheme = createTheme();

const customShadows: Shadows = [...defaultTheme.shadows];

export const brand = {
  50: '#fde8e9',
  100: '#f9b8ba',
  200: '#f4888b',
  300: '#ef585c',
  400: '#e63337',
  500: '#D71921',
  600: '#b8151c',
  700: '#991117',
  800: '#7a0d12',
  900: '#5b0a0d',
};

export const gray = {
  50: '#F5F5F5',
  100: '#E8E8E8',
  200: '#CCCCCC',
  300: '#999999',
  400: '#666666',
  500: '#555555',
  600: '#333333',
  700: '#1A1A1A',
  800: '#111111',
  900: '#000000',
};

export const green = {
  50: '#edf7ef',
  100: '#d2ebd7',
  200: '#a6d7af',
  300: '#79c387',
  400: '#5cb56d',
  500: '#4A9E5C',
  600: '#3d8a4e',
  700: '#2f6b3d',
  800: '#224d2c',
  900: '#152f1b',
};

export const orange = {
  50: '#fdf5e8',
  100: '#fbe5bf',
  200: '#f5d190',
  300: '#e8b960',
  400: '#D4A843',
  500: '#c09030',
  600: '#a07828',
  700: '#805f20',
  800: '#604718',
  900: '#402f10',
};

export const red = {
  50: '#fde8e9',
  100: '#f9b8ba',
  200: '#f4888b',
  300: '#ef585c',
  400: '#e63337',
  500: '#D71921',
  600: '#b8151c',
  700: '#991117',
  800: '#7a0d12',
  900: '#5b0a0d',
};

export const getDesignTokens = (mode: 'light' | 'dark') => {
  customShadows[1] = 'none';

  return {
    palette: {
      mode,
      primary: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: '#FFFFFF',
      },
      info: {
        light: '#5B9BF6',
        main: '#007AFF',
        dark: '#0055B3',
        contrastText: '#FFFFFF',
      },
      warning: {
        light: orange[300],
        main: orange[400],
        dark: orange[700],
      },
      error: {
        light: red[300],
        main: red[500],
        dark: red[700],
      },
      success: {
        light: green[300],
        main: green[500],
        dark: green[700],
      },
      grey: { ...gray },
      divider: mode === 'dark' ? '#222222' : '#E8E8E8',
      background: {
        default: mode === 'dark' ? '#000000' : '#F5F5F5',
        paper: mode === 'dark' ? '#111111' : '#FFFFFF',
      },
      text: {
        primary: mode === 'dark' ? '#E8E8E8' : '#1A1A1A',
        secondary: mode === 'dark' ? '#999999' : '#666666',
        disabled: mode === 'dark' ? '#666666' : '#999999',
      },
      action: {
        hover: mode === 'dark' ? alpha('#999999', 0.08) : alpha('#999999', 0.12),
        selected: mode === 'dark' ? alpha('#999999', 0.12) : alpha('#999999', 0.16),
      },
    },
    typography: {
      fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
      h1: {
        fontFamily: '"Doto", "Space Mono", monospace',
        fontSize: '4.5rem',
        fontWeight: 400,
        lineHeight: 1.0,
        letterSpacing: '-0.03em',
      },
      h2: {
        fontFamily: '"Doto", "Space Mono", monospace',
        fontSize: '3rem',
        fontWeight: 400,
        lineHeight: 1.05,
        letterSpacing: '-0.02em',
      },
      h3: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: '2.25rem',
        fontWeight: 500,
        lineHeight: 1.1,
        letterSpacing: '-0.02em',
      },
      h4: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: '1.5rem',
        fontWeight: 500,
        lineHeight: 1.2,
        letterSpacing: '-0.01em',
      },
      h5: {
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: defaultTheme.typography.pxToRem(18),
        fontWeight: 400,
        lineHeight: 1.3,
      },
      h6: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(16),
        fontWeight: 500,
        lineHeight: 1.3,
      },
      subtitle1: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(18),
        fontWeight: 400,
        lineHeight: 1.3,
      },
      subtitle2: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 500,
        lineHeight: 1.4,
      },
      body1: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(16),
        fontWeight: 400,
        lineHeight: 1.5,
      },
      body2: {
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 400,
        lineHeight: 1.5,
        letterSpacing: '0.01em',
      },
      caption: {
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: defaultTheme.typography.pxToRem(11),
        fontWeight: 400,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        lineHeight: 1.2,
      },
      overline: {
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: defaultTheme.typography.pxToRem(11),
        fontWeight: 400,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        lineHeight: 1.2,
      },
    },
    shape: {
      borderRadius: 8,
    },
    shadows: customShadows,
  };
};

export const colorSchemes = {
  light: {
    palette: {
      primary: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: '#FFFFFF',
      },
      info: {
        light: '#5B9BF6',
        main: '#007AFF',
        dark: '#0055B3',
        contrastText: '#FFFFFF',
      },
      warning: {
        light: orange[300],
        main: orange[400],
        dark: orange[700],
      },
      error: {
        light: red[300],
        main: red[500],
        dark: red[700],
      },
      success: {
        light: green[300],
        main: green[500],
        dark: green[700],
      },
      grey: { ...gray },
      divider: '#E8E8E8',
      background: {
        default: '#F5F5F5',
        paper: '#FFFFFF',
      },
      text: {
        primary: '#1A1A1A',
        secondary: '#666666',
      },
      action: {
        hover: alpha('#999999', 0.12),
        selected: alpha('#999999', 0.16),
      },
      baseShadow: 'none',
    },
  },
  dark: {
    palette: {
      primary: {
        contrastText: '#FFFFFF',
        light: brand[300],
        main: brand[500],
        dark: brand[700],
      },
      info: {
        light: '#5B9BF6',
        main: '#5B9BF6',
        dark: '#007AFF',
        contrastText: '#FFFFFF',
      },
      warning: {
        light: orange[300],
        main: orange[400],
        dark: orange[700],
      },
      error: {
        light: red[300],
        main: red[500],
        dark: red[700],
      },
      success: {
        light: green[300],
        main: green[500],
        dark: green[700],
      },
      grey: { ...gray },
      divider: '#222222',
      background: {
        default: '#000000',
        paper: '#111111',
      },
      text: {
        primary: '#E8E8E8',
        secondary: '#999999',
      },
      action: {
        hover: alpha('#999999', 0.08),
        selected: alpha('#999999', 0.12),
      },
      baseShadow: 'none',
    },
  },
};

export const typography = {
  fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
  h1: {
    fontFamily: '"Doto", "Space Mono", monospace',
    fontSize: '4.5rem',
    fontWeight: 400,
    lineHeight: 1.0,
    letterSpacing: '-0.03em',
  },
  h2: {
    fontFamily: '"Doto", "Space Mono", monospace',
    fontSize: '3rem',
    fontWeight: 400,
    lineHeight: 1.05,
    letterSpacing: '-0.02em',
  },
  h3: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: '2.25rem',
    fontWeight: 500,
    lineHeight: 1.1,
    letterSpacing: '-0.02em',
  },
  h4: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: '1.5rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: '-0.01em',
  },
  h5: {
    fontFamily: '"Space Mono", "JetBrains Mono", monospace',
    fontSize: defaultTheme.typography.pxToRem(18),
    fontWeight: 400,
    lineHeight: 1.3,
  },
  h6: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(16),
    fontWeight: 500,
    lineHeight: 1.3,
  },
  subtitle1: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(18),
    fontWeight: 400,
    lineHeight: 1.3,
  },
  subtitle2: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(14),
    fontWeight: 500,
    lineHeight: 1.4,
  },
  body1: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(16),
    fontWeight: 400,
    lineHeight: 1.5,
  },
  body2: {
    fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(14),
    fontWeight: 400,
    lineHeight: 1.5,
    letterSpacing: '0.01em',
  },
  caption: {
    fontFamily: '"Space Mono", "JetBrains Mono", monospace',
    fontSize: defaultTheme.typography.pxToRem(11),
    fontWeight: 400,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    lineHeight: 1.2,
  },
  overline: {
    fontFamily: '"Space Mono", "JetBrains Mono", monospace',
    fontSize: defaultTheme.typography.pxToRem(11),
    fontWeight: 400,
    letterSpacing: '0.08em',
    textTransform: 'uppercase' as const,
    lineHeight: 1.2,
  },
};

export const shape = {
  borderRadius: 8,
};

const defaultShadows: Shadows = [
  'none',
  'none',
  ...defaultTheme.shadows.slice(2).map(() => 'none'),
] as Shadows;
export const shadows = defaultShadows;
