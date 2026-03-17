import * as React from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ThemeOptions } from '@mui/material/styles';
import { inputsCustomizations } from './customizations/inputs';
import { dataDisplayCustomizations } from './customizations/dataDisplay';
import { feedbackCustomizations } from './customizations/feedback';
import { navigationCustomizations } from './customizations/navigation';
import { surfacesCustomizations } from './customizations/surfaces';
import { colorSchemes, typography, shadows, shape } from './themePrimitives';

interface AppThemeProps {
  children: React.ReactNode;
  /**
   * This is for the docs site. You can ignore it or remove it.
   */
  disableCustomTheme?: boolean;
  themeComponents?: ThemeOptions['components'];
}

export default function AppTheme(props: AppThemeProps) {
  const { children, disableCustomTheme, themeComponents } = props;
  const theme = React.useMemo(() => {
    return disableCustomTheme
      ? {}
      : createTheme({
          // For more details about CSS variables configuration, see https://mui.com/material-ui/customization/css-theme-variables/configuration/
          cssVariables: {
            colorSchemeSelector: 'data-mui-color-scheme',
            cssVarPrefix: 'template',
          },
          colorSchemes, // Recently added in v6 for building light & dark mode app, see https://mui.com/material-ui/customization/palette/#color-schemes
          typography,
          shadows,
          shape,
          components: {
            MuiCssBaseline: {
              styleOverrides: {
                '*': { boxSizing: 'border-box' },
                html: {
                  scrollBehavior: 'smooth',
                },
                body: {
                  minHeight: '100dvh',
                  backgroundImage:
                    'radial-gradient(circle at 12% 10%, hsla(174, 50%, 90%, 0.35), transparent 45%), radial-gradient(circle at 86% 14%, hsla(38, 80%, 85%, 0.35), transparent 40%), linear-gradient(135deg, hsla(40, 48%, 98%, 0.86), hsla(34, 38%, 96%, 0.9))',
                  backgroundAttachment: 'fixed',
                  textRendering: 'optimizeLegibility',
                  WebkitFontSmoothing: 'antialiased',
                },
                '[data-mui-color-scheme="dark"] body': {
                  backgroundImage:
                    'radial-gradient(circle at 12% 10%, hsla(174, 60%, 30%, 0.18), transparent 45%), radial-gradient(circle at 86% 14%, hsla(38, 70%, 35%, 0.15), transparent 40%), linear-gradient(135deg, hsla(22, 28%, 8%, 0.9), hsla(22, 22%, 10%, 0.9))',
                },
                '#root': {
                  minHeight: '100dvh',
                },
                '::selection': {
                  backgroundColor: 'hsla(174, 60%, 35%, 0.25)',
                },
                '*::-webkit-scrollbar': {
                  width: 10,
                  height: 10,
                },
                '*::-webkit-scrollbar-thumb': {
                  backgroundColor: 'hsla(174, 24%, 40%, 0.28)',
                  borderRadius: 999,
                  border: '2px solid transparent',
                  backgroundClip: 'content-box',
                },
                '*::-webkit-scrollbar-track': {
                  background: 'transparent',
                },
                '@keyframes riseIn': {
                  '0%': { opacity: 0, transform: 'translateY(12px)' },
                  '100%': { opacity: 1, transform: 'translateY(0px)' },
                },
                '@keyframes softPulse': {
                  '0%': { opacity: 0.55 },
                  '50%': { opacity: 0.9 },
                  '100%': { opacity: 0.55 },
                },
                '@media (prefers-reduced-motion: reduce)': {
                  '*, *::before, *::after': {
                    animationDuration: '0.01ms !important',
                    animationIterationCount: '1 !important',
                    transitionDuration: '0.01ms !important',
                    scrollBehavior: 'auto !important',
                  },
                },
              },
            },
            ...inputsCustomizations,
            ...dataDisplayCustomizations,
            ...feedbackCustomizations,
            ...navigationCustomizations,
            ...surfacesCustomizations,
            ...themeComponents,
          },
        });
  }, [disableCustomTheme, themeComponents]);
  if (disableCustomTheme) {
    return <React.Fragment>{children}</React.Fragment>;
  }
  return (
    <ThemeProvider theme={theme} disableTransitionOnChange>
      {children}
    </ThemeProvider>
  );
}
