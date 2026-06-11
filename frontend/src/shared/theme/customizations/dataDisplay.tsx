/* eslint-disable import/prefer-default-export */
import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { svgIconClasses } from '@mui/material/SvgIcon';
import { typographyClasses } from '@mui/material/Typography';
import { buttonBaseClasses } from '@mui/material/ButtonBase';
import { chipClasses } from '@mui/material/Chip';
import { iconButtonClasses } from '@mui/material/IconButton';
import { brand, fontText, tesla } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const dataDisplayCustomizations: Components<Theme> = {
  MuiList: {
    styleOverrides: {
      root: {
        padding: '8px',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      },
    },
  },
  MuiListItem: {
    styleOverrides: {
      root: ({ theme }) => ({
        [`& .${svgIconClasses.root}`]: {
          width: '1rem',
          height: '1rem',
          color: (theme.vars || theme).palette.text.secondary,
        },
        [`& .${typographyClasses.root}`]: {
          fontWeight: 400,
        },
        [`& .${buttonBaseClasses.root}`]: {
          display: 'flex',
          gap: 8,
          padding: '4px 16px',
          borderRadius: 4,
          minHeight: 32,
          opacity: 1,
          '&.Mui-selected': {
            backgroundColor: alpha(brand[500], 0.08),
            [`& .${svgIconClasses.root}`]: {
              color: brand[500],
            },
            '&:focus-visible': {
              backgroundColor: alpha(brand[500], 0.08),
            },
            '&:hover': {
              backgroundColor: alpha(brand[500], 0.12),
            },
          },
          '&:focus-visible': {
            backgroundColor: 'transparent',
          },
        },
      }),
    },
  },
  MuiListItemText: {
    styleOverrides: {
      primary: ({ theme }) => ({
        fontSize: theme.typography.body2.fontSize,
        fontWeight: 500,
        lineHeight: theme.typography.body2.lineHeight,
        fontFamily: fontText,
      }),
      secondary: ({ theme }) => ({
        fontSize: theme.typography.caption.fontSize,
        lineHeight: theme.typography.caption.lineHeight,
        fontFamily: fontText,
        color: tesla.pewter,
      }),
    },
  },
  MuiListSubheader: {
    styleOverrides: {
      root: ({ theme }) => ({
        backgroundColor: 'transparent',
        padding: '4px 16px',
        fontFamily: fontText,
        fontSize: '0.875rem',
        fontWeight: 500,
        letterSpacing: 'normal',
        textTransform: 'none' as const,
        lineHeight: theme.typography.caption.lineHeight,
        color: tesla.pewter,
      }),
    },
  },
  MuiListItemIcon: {
    styleOverrides: {
      root: {
        minWidth: 0,
      },
    },
  },
  MuiChip: {
    defaultProps: {
      size: 'small',
    },
    styleOverrides: {
      root: ({ theme }) => ({
        border: 'none',
        borderRadius: 4,
        fontFamily: fontText,
        textTransform: 'none' as const,
        letterSpacing: 'normal',
        [`& .${chipClasses.label}`]: {
          fontWeight: 500,
          fontSize: '0.75rem',
        },
        variants: [
          {
            props: { color: 'default' },
            style: {
              backgroundColor: tesla.lightAsh,
              [`& .${chipClasses.label}`]: {
                color: (theme.vars || theme).palette.text.secondary,
              },
              ...theme.applyStyles('dark', {
                backgroundColor: alpha(tesla.white, 0.08),
              }),
            },
          },
          {
            props: { color: 'success' },
            style: {
              backgroundColor: alpha('#4A9E5C', 0.1),
              [`& .${chipClasses.label}`]: {
                color: '#4A9E5C',
              },
            },
          },
          {
            props: { color: 'error' },
            style: {
              backgroundColor: alpha('#D71921', 0.1),
              [`& .${chipClasses.label}`]: {
                color: '#D71921',
              },
            },
          },
          {
            props: { color: 'warning' },
            style: {
              backgroundColor: alpha('#D4A843', 0.1),
              [`& .${chipClasses.label}`]: {
                color: '#D4A843',
              },
            },
          },
          {
            props: { color: 'primary' },
            style: {
              backgroundColor: alpha(brand[500], 0.1),
              [`& .${chipClasses.label}`]: {
                color: brand[500],
              },
            },
          },
          {
            props: { size: 'small' },
            style: {
              maxHeight: 24,
              [`& .${chipClasses.label}`]: {
                fontSize: '0.75rem',
              },
            },
          },
        ],
      }),
    },
  },
  MuiTablePagination: {
    styleOverrides: {
      actions: {
        display: 'flex',
        gap: 8,
        marginRight: 6,
        [`& .${iconButtonClasses.root}`]: {
          minWidth: 0,
          width: 36,
          height: 36,
        },
      },
    },
  },
  MuiIcon: {
    defaultProps: {
      fontSize: 'small',
    },
    styleOverrides: {
      root: {
        variants: [
          {
            props: { fontSize: 'small' },
            style: {
              fontSize: '1rem',
            },
          },
        ],
      },
    },
  },
};
