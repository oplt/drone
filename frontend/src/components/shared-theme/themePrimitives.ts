import { createTheme, alpha } from '@mui/material/styles';
import type { Shadows } from "@mui/material/styles";
import type { PaletteMode } from "@mui/material/styles";

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

  interface PaletteColor extends ColorRange {}

  interface Palette {
    baseShadow: string;
  }
}

const defaultTheme = createTheme();

const customShadows: Shadows = [...defaultTheme.shadows];

// Zapier Orange scale — #ff4f00 is the signature accent
export const brand = {
  50: '#fff3ee',
  100: '#ffe5d5',
  200: '#ffc9a8',
  300: '#ffaa7a',
  400: '#ff7a40',
  500: '#ff4f00',
  600: '#e04600',
  700: '#b83800',
  800: '#8a2900',
  900: '#5c1b00',
};

// Warm-tinted neutral scale — all values have reddish/yellowish warmth
export const gray = {
  50: '#fffefb',   // Cream White — page background
  100: '#fffdf9',  // Off-White — subtle alternate surface
  200: '#eceae3',  // Light Sand — secondary surfaces, ghost button bg
  300: '#c5c0b1',  // Sand — primary border color
  400: '#b5b2aa',  // Mid Warm — alternate borders
  500: '#939084',  // Warm Gray — muted/tertiary text
  600: '#36342e',  // Dark Charcoal — body text, footer text
  700: '#2d2b25',  // Warm dark
  800: '#201515',  // Zapier Black — headings, primary text
  900: '#160f0f',  // Near black
};

export const green = {
  50: 'hsl(145, 60%, 96%)',
  100: 'hsl(145, 55%, 90%)',
  200: 'hsl(145, 45%, 80%)',
  300: 'hsl(145, 40%, 66%)',
  400: 'hsl(145, 45%, 46%)',
  500: 'hsl(145, 55%, 34%)',
  600: 'hsl(145, 60%, 26%)',
  700: 'hsl(145, 65%, 20%)',
  800: 'hsl(145, 70%, 14%)',
  900: 'hsl(145, 75%, 10%)',
};

export const orange = {
  50: 'hsl(40, 100%, 97%)',
  100: 'hsl(38, 95%, 92%)',
  200: 'hsl(36, 85%, 82%)',
  300: 'hsl(34, 75%, 68%)',
  400: 'hsl(32, 70%, 52%)',
  500: 'hsl(30, 80%, 38%)',
  600: 'hsl(28, 85%, 28%)',
  700: 'hsl(26, 85%, 22%)',
  800: 'hsl(24, 90%, 16%)',
  900: 'hsl(22, 90%, 12%)',
};

export const red = {
  50: 'hsl(8, 85%, 96%)',
  100: 'hsl(8, 80%, 90%)',
  200: 'hsl(8, 75%, 80%)',
  300: 'hsl(8, 70%, 66%)',
  400: 'hsl(8, 70%, 52%)',
  500: 'hsl(8, 75%, 40%)',
  600: 'hsl(8, 80%, 30%)',
  700: 'hsl(8, 85%, 22%)',
  800: 'hsl(8, 88%, 16%)',
  900: 'hsl(8, 90%, 12%)',
};

export const getDesignTokens = (mode: PaletteMode) => {
  customShadows[1] = 'none';

  return {
    palette: {
      mode,
      primary: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: gray[50],
        ...(mode === 'dark' && {
          contrastText: gray[50],
          light: brand[300],
          main: brand[500],
          dark: brand[700],
        }),
      },
      info: {
        light: brand[100],
        main: brand[300],
        dark: brand[600],
        contrastText: gray[50],
        ...(mode === 'dark' && {
          contrastText: brand[200],
          light: brand[400],
          main: brand[600],
          dark: brand[900],
        }),
      },
      warning: {
        light: orange[300],
        main: orange[400],
        dark: orange[800],
        ...(mode === 'dark' && {
          light: orange[400],
          main: orange[500],
          dark: orange[700],
        }),
      },
      error: {
        light: red[300],
        main: red[400],
        dark: red[800],
        ...(mode === 'dark' && {
          light: red[400],
          main: red[500],
          dark: red[700],
        }),
      },
      success: {
        light: green[300],
        main: green[400],
        dark: green[800],
        ...(mode === 'dark' && {
          light: green[400],
          main: green[500],
          dark: green[700],
        }),
      },
      grey: {
        ...gray,
      },
      divider: mode === 'dark' ? alpha(gray[300], 0.15) : gray[300],
      background: {
        default: gray[50],
        paper: gray[100],
        ...(mode === 'dark' && {
          default: '#1a1210',
          paper: '#211916',
        }),
      },
      text: {
        primary: gray[800],
        secondary: gray[600],
        warning: orange[400],
        ...(mode === 'dark' && {
          primary: gray[50],
          secondary: gray[300],
        }),
      },
      action: {
        hover: alpha(gray[300], 0.2),
        selected: alpha(gray[300], 0.3),
        ...(mode === 'dark' && {
          hover: alpha(gray[300], 0.08),
          selected: alpha(gray[300], 0.12),
        }),
      },
    },
    typography: {
      fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
      h1: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: 'clamp(2.5rem, 5vw, 5rem)',
        fontWeight: 500,
        lineHeight: 0.90,
        letterSpacing: 0,
      },
      h2: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: 'clamp(2rem, 4vw, 3.5rem)',
        fontWeight: 500,
        lineHeight: 1.00,
        letterSpacing: 0,
      },
      h3: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: 'clamp(1.75rem, 3vw, 2.25rem)',
        fontWeight: 500,
        lineHeight: 1.04,
        letterSpacing: -0.5,
      },
      h4: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: 'clamp(1.5rem, 2vw, 1.75rem)',
        fontWeight: 500,
        lineHeight: 1.16,
      },
      h5: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(24),
        fontWeight: 600,
        letterSpacing: -0.48,
      },
      h6: {
        fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
        fontSize: defaultTheme.typography.pxToRem(18),
        fontWeight: 600,
        lineHeight: 1.00,
      },
      subtitle1: {
        fontSize: defaultTheme.typography.pxToRem(20),
        fontWeight: 400,
        lineHeight: 1.20,
        letterSpacing: -0.2,
      },
      subtitle2: {
        fontSize: defaultTheme.typography.pxToRem(16),
        fontWeight: 600,
        lineHeight: 1.16,
      },
      body1: {
        fontSize: defaultTheme.typography.pxToRem(16),
        fontWeight: 400,
        lineHeight: 1.25,
        letterSpacing: -0.16,
      },
      body2: {
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 500,
        lineHeight: 1.43,
      },
      caption: {
        fontSize: defaultTheme.typography.pxToRem(12),
        fontWeight: 600,
        letterSpacing: 0.5,
        textTransform: 'uppercase' as const,
      },
      overline: {
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 600,
        letterSpacing: 0.5,
        textTransform: 'uppercase' as const,
      },
    },
    shape: {
      borderRadius: 5,
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
        contrastText: gray[50],
      },
      info: {
        light: brand[100],
        main: brand[300],
        dark: brand[600],
        contrastText: gray[50],
      },
      warning: {
        light: orange[300],
        main: orange[400],
        dark: orange[800],
      },
      error: {
        light: red[300],
        main: red[400],
        dark: red[800],
      },
      success: {
        light: green[300],
        main: green[400],
        dark: green[800],
      },
      grey: {
        ...gray,
      },
      divider: gray[300],
      background: {
        default: gray[50],
        paper: gray[100],
      },
      text: {
        primary: gray[800],
        secondary: gray[600],
        warning: orange[400],
      },
      action: {
        hover: alpha(gray[300], 0.2),
        selected: alpha(gray[300], 0.3),
      },
      baseShadow: 'none',
    },
  },
  dark: {
    palette: {
      primary: {
        contrastText: gray[50],
        light: brand[300],
        main: brand[500],
        dark: brand[700],
      },
      info: {
        contrastText: brand[200],
        light: brand[400],
        main: brand[600],
        dark: brand[900],
      },
      warning: {
        light: orange[400],
        main: orange[500],
        dark: orange[700],
      },
      error: {
        light: red[400],
        main: red[500],
        dark: red[700],
      },
      success: {
        light: green[400],
        main: green[500],
        dark: green[700],
      },
      grey: {
        ...gray,
      },
      divider: alpha(gray[300], 0.15),
      background: {
        default: '#1a1210',
        paper: '#211916',
      },
      text: {
        primary: gray[50],
        secondary: gray[300],
      },
      action: {
        hover: alpha(gray[300], 0.08),
        selected: alpha(gray[300], 0.12),
      },
      baseShadow: 'none',
    },
  },
};

export const typography = {
  fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
  h1: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: 'clamp(2.5rem, 5vw, 5rem)',
    fontWeight: 500,
    lineHeight: 0.90,
    letterSpacing: 0,
  },
  h2: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: 'clamp(2rem, 4vw, 3.5rem)',
    fontWeight: 500,
    lineHeight: 1.00,
    letterSpacing: 0,
  },
  h3: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: 'clamp(1.75rem, 3vw, 2.25rem)',
    fontWeight: 500,
    lineHeight: 1.04,
    letterSpacing: -0.5,
  },
  h4: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: 'clamp(1.5rem, 2vw, 1.75rem)',
    fontWeight: 500,
    lineHeight: 1.16,
  },
  h5: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(24),
    fontWeight: 600,
    letterSpacing: -0.48,
  },
  h6: {
    fontFamily: '"Inter", "Helvetica Neue", Arial, sans-serif',
    fontSize: defaultTheme.typography.pxToRem(18),
    fontWeight: 600,
    lineHeight: 1.00,
  },
  subtitle1: {
    fontSize: defaultTheme.typography.pxToRem(20),
    fontWeight: 400,
    lineHeight: 1.20,
    letterSpacing: -0.2,
  },
  subtitle2: {
    fontSize: defaultTheme.typography.pxToRem(16),
    fontWeight: 600,
    lineHeight: 1.16,
  },
  body1: {
    fontSize: defaultTheme.typography.pxToRem(16),
    fontWeight: 400,
    lineHeight: 1.25,
    letterSpacing: -0.16,
  },
  body2: {
    fontSize: defaultTheme.typography.pxToRem(14),
    fontWeight: 500,
    lineHeight: 1.43,
  },
  caption: {
    fontSize: defaultTheme.typography.pxToRem(12),
    fontWeight: 600,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
  },
  overline: {
    fontSize: defaultTheme.typography.pxToRem(14),
    fontWeight: 600,
    letterSpacing: 0.5,
    textTransform: 'uppercase' as const,
  },
};

export const shape = {
  borderRadius: 5,
};

// @ts-ignore
const defaultShadows: Shadows = [
  'none',
  'var(--template-palette-baseShadow)',
  ...defaultTheme.shadows.slice(2),
];
export const shadows = defaultShadows;
