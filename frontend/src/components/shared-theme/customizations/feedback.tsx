import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { gray } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const feedbackCustomizations: Components<Theme> = {
  MuiAlert: {
    styleOverrides: {
      root: ({ theme, ownerState }) => {
        const severity = ownerState.severity ?? 'info';
        const palette = theme.palette[severity];

        return {
          borderRadius: 14,
          backgroundColor: alpha(palette.main, 0.08),
          color: (theme.vars || theme).palette.text.primary,
          border: `1px solid ${alpha(palette.main, 0.18)}`,
          '& .MuiAlert-icon': {
            color: palette.main,
          },
          ...theme.applyStyles('dark', {
            backgroundColor: alpha(palette.main, 0.18),
            border: `1px solid ${alpha(palette.main, 0.34)}`,
          }),
        };
      },
    },
  },
  MuiDialog: {
    styleOverrides: {
      root: ({ theme }) => ({
        '& .MuiDialog-paper': {
          borderRadius: '20px',
          border: '1px solid',
          borderColor: (theme.vars || theme).palette.divider,
        },
      }),
    },
  },
  MuiLinearProgress: {
    styleOverrides: {
      root: ({ theme }) => ({
        height: 8,
        borderRadius: 8,
        backgroundColor: gray[200],
        ...theme.applyStyles('dark', {
          backgroundColor: gray[800],
        }),
      }),
    },
  },
  MuiSkeleton: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 12,
        backgroundColor: alpha(theme.palette.text.primary, 0.07),
        ...theme.applyStyles('dark', {
          backgroundColor: alpha(theme.palette.common.white, 0.08),
        }),
      }),
    },
  },
};
