import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { gray } from '../themePrimitives';

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
        border: `1px solid ${gray[300]}`,
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
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(gray[300], 0.12)}`,
        }),
      }),
    },
  },
  MuiAccordionSummary: {
    styleOverrides: {
      root: ({ theme }) => ({
        border: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        '&:hover': { backgroundColor: gray[200] },
        '&:focus-visible': { backgroundColor: 'transparent' },
        ...theme.applyStyles('dark', {
          '&:hover': { backgroundColor: alpha(gray[300], 0.06) },
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
          gap: 20,
          transition: 'border-color 160ms ease',
          backgroundColor: gray[50],
          borderRadius: (theme.vars || theme).shape.borderRadius,
          border: `1px solid ${gray[300]}`,
          boxShadow: 'none',
          '@media (hover: hover)': {
            '&:hover': {
              borderColor: gray[400],
            },
          },
          ...theme.applyStyles('dark', {
            backgroundColor: '#211916',
            border: `1px solid ${alpha(gray[300], 0.12)}`,
            '@media (hover: hover)': {
              '&:hover': {
                borderColor: alpha(gray[300], 0.2),
              },
            },
          }),
          variants: [
            {
              props: { variant: 'outlined' },
              style: {
                border: `1px solid ${gray[300]}`,
                boxShadow: 'none',
                background: gray[50],
                ...theme.applyStyles('dark', {
                  background: alpha('#211916', 0.9),
                  border: `1px solid ${alpha(gray[300], 0.12)}`,
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
