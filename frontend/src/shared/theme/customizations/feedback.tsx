import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";

/* eslint-disable import/prefer-default-export */
export const feedbackCustomizations: Components<Theme> = {
  MuiAlert: {
    styleOverrides: {
      root: ({ theme, ownerState }) => {
        const severity = ownerState.severity ?? 'info';
        const colorMap: Record<string, string> = {
          error: '#D71921',
          warning: '#D4A843',
          success: '#4A9E5C',
          info: '#999999',
        };
        const accentColor = colorMap[severity] || '#999999';

        return {
          borderRadius: 8,
          backgroundColor: alpha(accentColor, 0.08),
          color: (theme.vars || theme).palette.text.primary,
          border: `1px solid ${alpha(accentColor, 0.2)}`,
          fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
          '& .MuiAlert-icon': {
            color: accentColor,
          },
          ...theme.applyStyles('dark', {
            backgroundColor: alpha(accentColor, 0.12),
            border: `1px solid ${alpha(accentColor, 0.25)}`,
          }),
        };
      },
    },
  },
  MuiDialog: {
    styleOverrides: {
      root: ({ theme }) => ({
        '& .MuiDialog-paper': {
          borderRadius: 16,
          border: '1px solid',
          borderColor: '#333333',
          backgroundImage: 'none',
          backgroundColor: (theme.vars || theme).palette.background.paper,
          boxShadow: 'none',
        },
      }),
    },
  },
  MuiLinearProgress: {
    styleOverrides: {
      root: ({ theme }) => ({
        height: 4,
        borderRadius: 0,
        backgroundColor: '#222222',
        ...theme.applyStyles('dark', {
          backgroundColor: '#222222',
        }),
        '& .MuiLinearProgress-bar': {
          borderRadius: 0,
        },
      }),
    },
  },
  MuiSkeleton: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 4,
        backgroundColor: alpha('#999999', 0.08),
        ...theme.applyStyles('dark', {
          backgroundColor: alpha('#999999', 0.08),
        }),
      }),
    },
  },
};
