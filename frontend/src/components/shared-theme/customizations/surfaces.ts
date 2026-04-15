import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";

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
        backgroundColor: (theme.vars || theme).palette.background.default,
        border: '1px solid',
        borderColor: (theme.vars || theme).palette.divider,
        boxShadow: 'none',
        ':before': {
          backgroundColor: 'transparent',
        },
        '&:not(:last-of-type)': {
          borderBottom: 'none',
        },
        '&:first-of-type': {
          borderTopLeftRadius: (theme.vars || theme).shape.borderRadius,
          borderTopRightRadius: (theme.vars || theme).shape.borderRadius,
        },
        '&:last-of-type': {
          borderBottomLeftRadius: (theme.vars || theme).shape.borderRadius,
          borderBottomRightRadius: (theme.vars || theme).shape.borderRadius,
        },
      }),
    },
  },
  MuiAccordionSummary: {
    styleOverrides: {
      root: ({ theme }) => ({
        border: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        '&:hover': { backgroundColor: alpha('#999999', 0.06) },
        '&:focus-visible': { backgroundColor: 'transparent' },
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
          gap: 20,
          transition: 'border-color 150ms cubic-bezier(0.25, 0.1, 0.25, 1)',
          backgroundColor: (theme.vars || theme).palette.background.paper,
          borderRadius: 16,
          border: '1px solid',
          borderColor: (theme.vars || theme).palette.divider,
          boxShadow: 'none',
          '@media (hover: hover)': {
            '&:hover': {
              borderColor: '#333333',
            },
          },
          ...theme.applyStyles('dark', {
            '@media (hover: hover)': {
              '&:hover': {
                borderColor: '#333333',
              },
            },
          }),
          variants: [
            {
              props: { variant: 'outlined' },
              style: {
                border: '1px solid',
                borderColor: (theme.vars || theme).palette.divider,
                boxShadow: 'none',
                ...theme.applyStyles('dark', {
                  borderColor: '#222222',
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
