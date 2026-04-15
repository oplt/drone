import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { svgIconClasses } from '@mui/material/SvgIcon';
import { typographyClasses } from '@mui/material/Typography';
import { buttonBaseClasses } from '@mui/material/ButtonBase';
import { chipClasses } from '@mui/material/Chip';
import { iconButtonClasses } from '@mui/material/IconButton';

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
          padding: '2px 8px',
          borderRadius: (theme.vars || theme).shape.borderRadius,
          opacity: 0.7,
          '&.Mui-selected': {
            opacity: 1,
            backgroundColor: alpha('#999999', 0.12),
            [`& .${svgIconClasses.root}`]: {
              color: (theme.vars || theme).palette.text.primary,
            },
            '&:focus-visible': {
              backgroundColor: alpha('#999999', 0.12),
            },
            '&:hover': {
              backgroundColor: alpha('#999999', 0.16),
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
        fontWeight: 400,
        lineHeight: theme.typography.body2.lineHeight,
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
      }),
      secondary: ({ theme }) => ({
        fontSize: theme.typography.caption.fontSize,
        lineHeight: theme.typography.caption.lineHeight,
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
      }),
    },
  },
  MuiListSubheader: {
    styleOverrides: {
      root: ({ theme }) => ({
        backgroundColor: 'transparent',
        padding: '4px 8px',
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.6875rem',
        fontWeight: 400,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        lineHeight: theme.typography.caption.lineHeight,
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
        border: '1px solid',
        borderRadius: 4,
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        textTransform: 'uppercase' as const,
        letterSpacing: '0.04em',
        [`& .${chipClasses.label}`]: {
          fontWeight: 400,
          fontSize: '0.6875rem',
        },
        variants: [
          {
            props: { color: 'default' },
            style: {
              borderColor: '#333333',
              backgroundColor: 'transparent',
              [`& .${chipClasses.label}`]: {
                color: (theme.vars || theme).palette.text.secondary,
              },
              ...theme.applyStyles('dark', {
                borderColor: '#333333',
              }),
            },
          },
          {
            props: { color: 'success' },
            style: {
              borderColor: alpha('#4A9E5C', 0.3),
              backgroundColor: alpha('#4A9E5C', 0.08),
              [`& .${chipClasses.label}`]: {
                color: '#4A9E5C',
              },
            },
          },
          {
            props: { color: 'error' },
            style: {
              borderColor: alpha('#D71921', 0.3),
              backgroundColor: alpha('#D71921', 0.08),
              [`& .${chipClasses.label}`]: {
                color: '#D71921',
              },
            },
          },
          {
            props: { color: 'warning' },
            style: {
              borderColor: alpha('#D4A843', 0.3),
              backgroundColor: alpha('#D4A843', 0.08),
              [`& .${chipClasses.label}`]: {
                color: '#D4A843',
              },
            },
          },
          {
            props: { color: 'primary' },
            style: {
              borderColor: alpha('#D71921', 0.3),
              backgroundColor: alpha('#D71921', 0.08),
              [`& .${chipClasses.label}`]: {
                color: '#D71921',
              },
            },
          },
          {
            props: { size: 'small' },
            style: {
              maxHeight: 22,
              [`& .${chipClasses.label}`]: {
                fontSize: '0.625rem',
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
