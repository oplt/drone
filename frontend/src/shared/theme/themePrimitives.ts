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

/** Tesla-inspired design tokens (DESIGN.md) */
export const tesla = {
  electricBlue: '#3E6AE1',
  white: '#FFFFFF',
  lightAsh: '#F4F4F4',
  carbonDark: '#171A20',
  graphite: '#393C41',
  pewter: '#5C5E62',
  silverFog: '#8E8E8E',
  cloudGray: '#EEEEEE',
  paleSilver: '#D0D1D2',
  frostedGlass: 'rgba(255, 255, 255, 0.75)',
};

export const fontDisplay =
  '"Universal Sans Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
export const fontText =
  '"Universal Sans Text", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';

export const teslaTransition =
  'border-color 0.33s cubic-bezier(0.5, 0, 0, 0.75), background-color 0.33s cubic-bezier(0.5, 0, 0, 0.75), color 0.33s cubic-bezier(0.5, 0, 0, 0.75), box-shadow 0.25s cubic-bezier(0.5, 0, 0, 0.75)';

export const brand = {
  50: '#EBF0FC',
  100: '#C5D4F5',
  200: '#9FB8EE',
  300: '#799CE7',
  400: '#5E84E4',
  500: tesla.electricBlue,
  600: '#355BC0',
  700: '#2C4C9F',
  800: '#233D7E',
  900: '#1A2E5D',
};

export const gray = {
  50: tesla.lightAsh,
  100: tesla.cloudGray,
  200: tesla.paleSilver,
  300: tesla.silverFog,
  400: tesla.pewter,
  500: tesla.graphite,
  600: tesla.carbonDark,
  700: '#12151A',
  800: '#0D0F12',
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
        contrastText: tesla.white,
      },
      info: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: tesla.white,
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
      divider: mode === 'dark' ? alpha(tesla.white, 0.12) : tesla.cloudGray,
      background: {
        default: mode === 'dark' ? tesla.carbonDark : tesla.white,
        paper: mode === 'dark' ? tesla.carbonDark : tesla.white,
      },
      text: {
        primary: mode === 'dark' ? tesla.white : tesla.carbonDark,
        secondary: mode === 'dark' ? tesla.silverFog : tesla.graphite,
        disabled: tesla.silverFog,
      },
      action: {
        hover: mode === 'dark' ? alpha(tesla.white, 0.06) : alpha(tesla.carbonDark, 0.04),
        selected: mode === 'dark' ? alpha(tesla.white, 0.08) : alpha(tesla.electricBlue, 0.08),
      },
    },
    typography: {
      fontFamily: fontText,
      h1: {
        fontFamily: fontDisplay,
        fontSize: '2.5rem',
        fontWeight: 500,
        lineHeight: 1.2,
        letterSpacing: 'normal',
      },
      h2: {
        fontFamily: fontDisplay,
        fontSize: '2rem',
        fontWeight: 500,
        lineHeight: 1.2,
        letterSpacing: 'normal',
      },
      h3: {
        fontFamily: fontDisplay,
        fontSize: '1.5rem',
        fontWeight: 500,
        lineHeight: 1.2,
        letterSpacing: 'normal',
      },
      h4: {
        fontFamily: fontText,
        fontSize: '1.0625rem',
        fontWeight: 500,
        lineHeight: 1.18,
        letterSpacing: 'normal',
      },
      h5: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(16),
        fontWeight: 500,
        lineHeight: 1.25,
      },
      h6: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 500,
        lineHeight: 1.2,
      },
      subtitle1: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(17),
        fontWeight: 500,
        lineHeight: 1.18,
      },
      subtitle2: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 500,
        lineHeight: 1.2,
      },
      body1: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 400,
        lineHeight: 1.43,
      },
      body2: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 400,
        lineHeight: 1.43,
        letterSpacing: 'normal',
      },
      caption: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(12),
        fontWeight: 400,
        letterSpacing: 'normal',
        lineHeight: 1.43,
      },
      overline: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(12),
        fontWeight: 500,
        letterSpacing: 'normal',
        lineHeight: 1.2,
      },
      button: {
        fontFamily: fontText,
        fontSize: defaultTheme.typography.pxToRem(14),
        fontWeight: 500,
        lineHeight: 1.2,
        textTransform: 'none' as const,
      },
    },
    shape: {
      borderRadius: 4,
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
        contrastText: tesla.white,
      },
      info: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: tesla.white,
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
      divider: tesla.cloudGray,
      background: {
        default: tesla.white,
        paper: tesla.white,
      },
      text: {
        primary: tesla.carbonDark,
        secondary: tesla.graphite,
        disabled: tesla.silverFog,
      },
      action: {
        hover: alpha(tesla.carbonDark, 0.04),
        selected: alpha(tesla.electricBlue, 0.08),
      },
      baseShadow: 'none',
    },
  },
  dark: {
    palette: {
      primary: {
        contrastText: tesla.white,
        light: brand[300],
        main: brand[500],
        dark: brand[700],
      },
      info: {
        light: brand[300],
        main: brand[500],
        dark: brand[700],
        contrastText: tesla.white,
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
      divider: alpha(tesla.white, 0.12),
      background: {
        default: tesla.carbonDark,
        paper: tesla.carbonDark,
      },
      text: {
        primary: tesla.white,
        secondary: tesla.silverFog,
        disabled: tesla.pewter,
      },
      action: {
        hover: alpha(tesla.white, 0.06),
        selected: alpha(tesla.electricBlue, 0.16),
      },
      baseShadow: 'none',
    },
  },
};

export const typography = getDesignTokens('light').typography;

export const shape = {
  borderRadius: 4,
};

const defaultShadows: Shadows = [
  'none',
  'none',
  ...defaultTheme.shadows.slice(2).map(() => 'none'),
] as Shadows;
export const shadows = defaultShadows;
