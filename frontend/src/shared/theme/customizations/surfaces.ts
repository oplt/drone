import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { radius, shape, tesla, teslaTransition } from '../themePrimitives';

const panelRadius = shape.borderRadius * radius.md;
const overlayRadius = shape.borderRadius * radius.sm;

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
          borderTopLeftRadius: theme.shape.borderRadius,
          borderTopRightRadius: theme.shape.borderRadius,
        },
        '&:last-of-type': {
          borderBottomLeftRadius: theme.shape.borderRadius,
          borderBottomRightRadius: theme.shape.borderRadius,
        },
      }),
    },
  },
  MuiAccordionSummary: {
    styleOverrides: {
      root: ({ theme }) => ({
        border: 'none',
        borderRadius: theme.shape.borderRadius,
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
        variants: [
          {
            props: { variant: 'opsPanel' },
            style: {
              borderRadius: panelRadius,
              border: '1px solid',
              borderColor: (theme.vars || theme).palette.divider,
              backgroundColor: (theme.vars || theme).palette.background.paper,
              boxShadow: 'none',
            },
          },
          {
            props: { variant: 'mapOverlay' },
            style: {
              borderRadius: overlayRadius,
              border: '1px solid',
              borderColor: (theme.vars || theme).palette.divider,
              backgroundColor: (theme.vars || theme).palette.surface.overlay,
              backdropFilter: 'blur(4px)',
              boxShadow: 'none',
            },
          },
          {
            props: { variant: 'quiet' },
            style: {
              borderRadius: panelRadius,
              border: 'none',
              backgroundColor: 'transparent',
              boxShadow: 'none',
            },
          },
        ],
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
          borderRadius: panelRadius,
          border: 'none',
          boxShadow: 'none',
          variants: [
            {
              props: { variant: 'outlined' },
              style: {
                border: '1px solid',
                borderColor: (theme.vars || theme).palette.divider,
                backgroundColor: (theme.vars || theme).palette.surface.raised,
                boxShadow: 'none',
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
