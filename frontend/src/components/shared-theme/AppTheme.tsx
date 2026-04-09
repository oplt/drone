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
          cssVariables: {
            colorSchemeSelector: 'data-mui-color-scheme',
            cssVarPrefix: 'template',
          },
          colorSchemes,
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
                  backgroundColor: '#fffefb',
                  textRendering: 'optimizeLegibility',
                  WebkitFontSmoothing: 'antialiased',
                },
                '[data-mui-color-scheme="dark"] body': {
                  backgroundColor: '#1a1210',
                },
                '#root': {
                  minHeight: '100dvh',
                },
                '::selection': {
                  backgroundColor: 'rgba(255, 79, 0, 0.15)',
                },
                '*::-webkit-scrollbar': {
                  width: 10,
                  height: 10,
                },
                '*::-webkit-scrollbar-thumb': {
                  backgroundColor: 'rgba(197, 192, 177, 0.5)',
                  borderRadius: 5,
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
