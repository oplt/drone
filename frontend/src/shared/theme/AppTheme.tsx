import * as React from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ThemeOptions } from '@mui/material/styles';
import { inputsCustomizations } from './customizations/inputs';
import { dataDisplayCustomizations } from './customizations/dataDisplay';
import { feedbackCustomizations } from './customizations/feedback';
import { navigationCustomizations } from './customizations/navigation';
import { surfacesCustomizations } from './customizations/surfaces';
import { colorSchemes, typography, shadows, shape, tesla } from './themePrimitives';

interface AppThemeProps {
  children: React.ReactNode;
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
                  backgroundColor: tesla.white,
                  textRendering: 'optimizeLegibility',
                  WebkitFontSmoothing: 'antialiased',
                },
                '[data-mui-color-scheme="dark"] body': {
                  backgroundColor: tesla.carbonDark,
                },
                '#root': {
                  minHeight: '100dvh',
                },
                '::selection': {
                  backgroundColor: 'rgba(62, 106, 225, 0.2)',
                },
                '*::-webkit-scrollbar': {
                  width: 6,
                  height: 6,
                },
                '*::-webkit-scrollbar-thumb': {
                  backgroundColor: 'rgba(142, 142, 142, 0.5)',
                  borderRadius: 4,
                },
                '*::-webkit-scrollbar-track': {
                  background: 'transparent',
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
