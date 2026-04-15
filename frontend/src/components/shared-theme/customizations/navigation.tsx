import * as React from 'react';
import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import type { SvgIconProps } from "@mui/material/SvgIcon";
import { buttonBaseClasses } from '@mui/material/ButtonBase';
import { dividerClasses } from '@mui/material/Divider';
import { menuItemClasses } from '@mui/material/MenuItem';
import { selectClasses } from '@mui/material/Select';
import { tabClasses } from '@mui/material/Tab';
import UnfoldMoreRoundedIcon from '@mui/icons-material/UnfoldMoreRounded';

/* eslint-disable import/prefer-default-export */
export const navigationCustomizations: Components<Theme> = {
  MuiMenuItem: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: (theme.vars || theme).shape.borderRadius,
        padding: '6px 8px',
        fontFamily: '"Space Grotesk", "DM Sans", system-ui, sans-serif',
        [`&.${menuItemClasses.focusVisible}`]: {
          backgroundColor: 'transparent',
        },
        [`&.${menuItemClasses.selected}`]: {
          [`&.${menuItemClasses.focusVisible}`]: {
            backgroundColor: alpha('#999999', 0.12),
          },
        },
      }),
    },
  },
  MuiMenu: {
    styleOverrides: {
      list: {
        gap: '0px',
        [`&.${dividerClasses.root}`]: {
          margin: '0 -8px',
        },
      },
      paper: ({ theme }) => ({
        marginTop: '4px',
        borderRadius: 8,
        border: '1px solid',
        borderColor: '#333333',
        backgroundImage: 'none',
        background: (theme.vars || theme).palette.background.paper,
        boxShadow: 'none',
        [`& .${buttonBaseClasses.root}`]: {
          '&.Mui-selected': {
            backgroundColor: alpha('#999999', 0.12),
          },
        },
      }),
    },
  },
  MuiSelect: {
    defaultProps: {
      IconComponent: React.forwardRef<SVGSVGElement, SvgIconProps>((props, ref) => (
        <UnfoldMoreRoundedIcon fontSize="small" {...props} ref={ref} />
      )),
    },
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 8,
        border: '1px solid',
        borderColor: '#333333',
        backgroundColor: 'transparent',
        boxShadow: 'none',
        '&:hover': {
          borderColor: (theme.vars || theme).palette.text.primary,
          boxShadow: 'none',
        },
        [`&.${selectClasses.focused}`]: {
          outlineOffset: 0,
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        '&:before, &:after': {
          display: 'none',
        },
      }),
      select: {
        display: 'flex',
        alignItems: 'center',
      },
    },
  },
  MuiLink: {
    defaultProps: {
      underline: 'none',
    },
    styleOverrides: {
      root: ({ theme }) => ({
        color: (theme.vars || theme).palette.text.primary,
        fontWeight: 500,
        position: 'relative',
        textDecoration: 'none',
        width: 'fit-content',
        '&::before': {
          content: '""',
          position: 'absolute',
          width: '100%',
          height: '1px',
          bottom: 0,
          left: 0,
          backgroundColor: (theme.vars || theme).palette.text.secondary,
          opacity: 0.4,
          transition: 'width 200ms cubic-bezier(0.25, 0.1, 0.25, 1), opacity 200ms cubic-bezier(0.25, 0.1, 0.25, 1)',
        },
        '&:hover::before': {
          width: 0,
        },
        '&:focus-visible': {
          outline: `1px solid ${(theme.vars || theme).palette.text.primary}`,
          outlineOffset: '4px',
          borderRadius: '2px',
        },
      }),
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: ({ theme }) => ({
        backgroundColor: (theme.vars || theme).palette.background.default,
        borderRight: '1px solid',
        borderColor: (theme.vars || theme).palette.divider,
      }),
    },
  },
  MuiPaginationItem: {
    styleOverrides: {
      root: ({ theme }) => ({
        '&.Mui-selected': {
          color: (theme.vars || theme).palette.background.default,
          backgroundColor: (theme.vars || theme).palette.text.primary,
        },
      }),
    },
  },
  MuiTabs: {
    styleOverrides: {
      root: { minHeight: 'fit-content' },
      indicator: {
        backgroundColor: 'transparent',
      },
    },
  },
  MuiTab: {
    styleOverrides: {
      root: ({ theme }) => ({
        padding: '12px 16px',
        marginBottom: '0px',
        textTransform: 'uppercase',
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.6875rem',
        letterSpacing: '0.06em',
        minWidth: 'fit-content',
        minHeight: 'fit-content',
        fontWeight: 400,
        color: (theme.vars || theme).palette.text.secondary,
        borderRadius: 0,
        border: 'none',
        boxShadow: 'none',
        ':hover': {
          color: (theme.vars || theme).palette.text.primary,
          backgroundColor: 'transparent',
          boxShadow: `${(theme.vars || theme).palette.text.secondary} 0px -2px 0px 0px inset`,
        },
        [`&.${tabClasses.selected}`]: {
          color: (theme.vars || theme).palette.text.primary,
          fontWeight: 700,
          boxShadow: `#D71921 0px -2px 0px 0px inset`,
        },
      }),
    },
  },
  MuiStepConnector: {
    styleOverrides: {
      line: ({ theme }) => ({
        borderTop: '1px solid',
        borderColor: (theme.vars || theme).palette.divider,
        flex: 1,
        borderRadius: '99px',
      }),
    },
  },
  MuiStepIcon: {
    styleOverrides: {
      root: ({ theme }) => ({
        color: 'transparent',
        border: '1px solid',
        borderColor: '#333333',
        width: 12,
        height: 12,
        borderRadius: '50%',
        '& text': {
          display: 'none',
        },
        '&.Mui-active': {
          border: 'none',
          color: '#D71921',
        },
        '&.Mui-completed': {
          border: 'none',
          color: '#4A9E5C',
        },
        variants: [
          {
            props: { completed: true },
            style: {
              width: 12,
              height: 12,
            },
          },
        ],
      }),
    },
  },
  MuiStepLabel: {
    styleOverrides: {
      label: ({ theme }) => ({
        '&.Mui-completed': {
          opacity: 0.6,
          ...theme.applyStyles('dark', { opacity: 0.5 }),
        },
      }),
    },
  },
};
