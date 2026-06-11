import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { tesla, teslaTransition } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const surfacesCustomizations: Components<Theme> = {
  MuiAccordion: {
    defaultProps: {
      elevation: 0,
      disableGutters: true,
    },
    styleOverrides: {
      root: ({ theme }) => ({
        padding: 4,
        overflow: 'clip',
        backgroundColor: (theme.vars || theme).palette.background.paper,
        border: 'none',
        boxShadow: 'none',
        ':before': {
          backgroundColor: 'transparent',
        },
        '&:not(:last-of-type)': {
          borderBottom: `1px solid ${(theme.vars || theme).palette.divider}`,
        },
        '&:first-of-type': {
          borderTopLeftRadius: 4,
          borderTopRightRadius: 4,
        },
        '&:last-of-type': {
          borderBottomLeftRadius: 4,
          borderBottomRightRadius: 4,
        },
      }),
    },
  },
  MuiAccordionSummary: {
    styleOverrides: {
      root: ({ theme }) => ({
        border: 'none',
        borderRadius: 4,
        transition: teslaTransition,
        '&:hover': { backgroundColor: alpha(tesla.carbonDark, 0.04) },
        '&:focus-visible': { backgroundColor: 'transparent' },
        ...theme.applyStyles('dark', {
          '&:hover': { backgroundColor: alpha(tesla.white, 0.04) },
        }),
      }),
    },
  },
  MuiAccordionDetails: {
    styleOverrides: {
      root: { mb: 20, border: 'none' },
    },
  },
  MuiPaper: {
    defaultProps: {
      elevation: 0,
    },
    styleOverrides: {
      root: ({ theme }) => ({
        backgroundImage: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        boxShadow: 'none',
      }),
    },
  },
  MuiCard: {
    styleOverrides: {
      root: ({ theme }) => {
        return {
          padding: 20,
          gap: 16,
          transition: teslaTransition,
          backgroundColor: (theme.vars || theme).palette.background.paper,
          borderRadius: 12,
          border: 'none',
          boxShadow: 'none',
          variants: [
            {
              props: { variant: 'outlined' },
              style: {
                border: 'none',
                backgroundColor: tesla.lightAsh,
                boxShadow: 'none',
                ...theme.applyStyles('dark', {
                  backgroundColor: alpha(tesla.white, 0.04),
                }),
              },
            },
          ],
        };
      },
    },
  },
  MuiCardContent: {
    styleOverrides: {
      root: {
        padding: 0,
        '&:last-child': { paddingBottom: 0 },
      },
    },
  },
  MuiCardHeader: {
    styleOverrides: {
      root: {
        padding: 0,
      },
    },
  },
  MuiCardActions: {
    styleOverrides: {
      root: {
        padding: 0,
      },
    },
  },
};
