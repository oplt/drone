import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { fontText, tesla } from '../themePrimitives';

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
          info: tesla.pewter,
        };
        const accentColor = colorMap[severity] || tesla.pewter;

        return {
          borderRadius: 4,
          backgroundColor: alpha(accentColor, 0.08),
          color: (theme.vars || theme).palette.text.primary,
          border: 'none',
          fontFamily: fontText,
          '& .MuiAlert-icon': {
            color: accentColor,
          },
          ...theme.applyStyles('dark', {
            backgroundColor: alpha(accentColor, 0.12),
          }),
        };
      },
    },
  },
  MuiDialog: {
    styleOverrides: {
      root: ({ theme }) => ({
        '& .MuiDialog-paper': {
          borderRadius: 4,
          border: 'none',
          backgroundImage: 'none',
          backgroundColor: (theme.vars || theme).palette.background.paper,
          boxShadow: 'none',
        },
        '& .MuiBackdrop-root': {
          backgroundColor: 'rgba(128, 128, 128, 0.65)',
        },
      }),
    },
  },
  MuiLinearProgress: {
    styleOverrides: {
      root: ({ theme }) => ({
        height: 4,
        borderRadius: 0,
        backgroundColor: tesla.cloudGray,
        ...theme.applyStyles('dark', {
          backgroundColor: alpha(tesla.white, 0.12),
        }),
        '& .MuiLinearProgress-bar': {
          borderRadius: 0,
          backgroundColor: theme.palette.primary.main,
        },
      }),
    },
  },
  MuiSkeleton: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 4,
        backgroundColor: alpha(tesla.carbonDark, 0.06),
        ...theme.applyStyles('dark', {
          backgroundColor: alpha(tesla.white, 0.08),
        }),
      }),
    },
  },
};
