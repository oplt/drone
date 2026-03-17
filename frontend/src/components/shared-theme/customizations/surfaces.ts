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
        border: '1px solid',
        borderColor: (theme.vars || theme).palette.divider,
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
        borderRadius: 8,
        '&:hover': { backgroundColor: gray[50] },
        '&:focus-visible': { backgroundColor: 'transparent' },
        ...theme.applyStyles('dark', {
          '&:hover': { backgroundColor: gray[800] },
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
      }),
    },
  },
  MuiCard: {
    styleOverrides: {
      root: ({ theme }) => {
        const cardRadius = (theme.vars || theme).shape.borderRadius;
        return {
          padding: 20,
          gap: 20,
          transition: 'transform 160ms ease, box-shadow 200ms ease, border-color 160ms ease',
          backgroundColor: alpha(gray[50], 0.95),
          borderRadius: typeof cardRadius === 'number' ? cardRadius + 6 : cardRadius,
          border: `1px solid ${alpha(gray[200], 0.8)}`,
          boxShadow: (theme.vars || theme).palette.baseShadow,
          '@media (hover: hover)': {
            '&:hover': {
              borderColor: alpha(gray[300], 0.9),
              boxShadow: `0 18px 34px ${alpha(gray[700], 0.08)}`,
              transform: 'translateY(-3px)',
            },
          },
          ...theme.applyStyles('dark', {
            backgroundColor: alpha(gray[800], 0.9),
            borderColor: alpha(gray[700], 0.6),
            '@media (hover: hover)': {
              '&:hover': {
                borderColor: alpha(gray[600], 0.7),
                boxShadow: `0 18px 36px ${alpha(gray[900], 0.6)}`,
                transform: 'translateY(-3px)',
              },
            },
          }),
          variants: [
            {
              props: {
                variant: 'outlined',
              },
              style: {
                border: `1px solid ${alpha(gray[200], 0.8)}`,
                boxShadow: (theme.vars || theme).palette.baseShadow,
                background: 'rgba(255, 255, 255, 0.82)',
                backdropFilter: 'blur(12px)',
                ...theme.applyStyles('dark', {
                  background: alpha(gray[900], 0.52),
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
