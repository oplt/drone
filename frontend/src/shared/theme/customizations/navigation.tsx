/* eslint-disable import/prefer-default-export */
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
import { brand, fontText, tesla, teslaTransition } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const navigationCustomizations: Components<Theme> = {
  MuiMenuItem: {
    styleOverrides: {
      root: ({ theme: muiTheme }) => ({
        borderRadius: (muiTheme.vars || muiTheme).shape.borderRadius,
        padding: '6px 8px',
        fontFamily: fontText,
        transition: teslaTransition,
        [`&.${menuItemClasses.focusVisible}`]: {
          backgroundColor: 'transparent',
        },
        [`&.${menuItemClasses.selected}`]: {
          [`&.${menuItemClasses.focusVisible}`]: {
            backgroundColor: alpha(brand[500], 0.08),
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
        borderRadius: 4,
        border: 'none',
        backgroundImage: 'none',
        background: (theme.vars || theme).palette.background.paper,
        boxShadow: 'none',
        [`& .${buttonBaseClasses.root}`]: {
          '&.Mui-selected': {
            backgroundColor: alpha(brand[500], 0.08),
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
      root: () => ({
        borderRadius: 4,
        border: `1px solid ${tesla.paleSilver}`,
        backgroundColor: 'transparent',
        boxShadow: 'none',
        transition: teslaTransition,
        '&:hover': {
          borderColor: tesla.silverFog,
          boxShadow: 'none',
        },
        [`&.${selectClasses.focused}`]: {
          outlineOffset: 0,
          borderColor: brand[500],
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
        color: tesla.pewter,
        fontWeight: 400,
        fontSize: '0.875rem',
        position: 'relative',
        textDecoration: 'none',
        width: 'fit-content',
        transition: teslaTransition,
        '&:hover': {
          color: tesla.graphite,
          textDecoration: 'underline',
        },
        '&:focus-visible': {
          outline: `2px solid ${(theme.vars || theme).palette.primary.main}`,
          outlineOffset: '4px',
          borderRadius: '2px',
        },
      }),
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: ({ theme }) => ({
        backgroundColor: (theme.vars || theme).palette.background.paper,
        borderRight: 'none',
        boxShadow: 'none',
      }),
    },
  },
  MuiPaginationItem: {
    styleOverrides: {
      root: () => ({
        borderRadius: 4,
        transition: teslaTransition,
        '&.Mui-selected': {
          color: tesla.white,
          backgroundColor: brand[500],
        },
      }),
    },
  },
  MuiTabs: {
    styleOverrides: {
      root: { minHeight: 'fit-content' },
      indicator: {
        backgroundColor: brand[500],
        height: 2,
      },
    },
  },
  MuiTab: {
    styleOverrides: {
      root: ({ theme }) => ({
        padding: '12px 16px',
        marginBottom: '0px',
        textTransform: 'none',
        fontFamily: fontText,
        fontSize: '0.875rem',
        letterSpacing: 'normal',
        minWidth: 'fit-content',
        minHeight: 'fit-content',
        fontWeight: 500,
        color: (theme.vars || theme).palette.text.secondary,
        borderRadius: 4,
        border: 'none',
        boxShadow: 'none',
        transition: teslaTransition,
        ':hover': {
          color: (theme.vars || theme).palette.text.primary,
          backgroundColor: alpha(tesla.carbonDark, 0.04),
        },
        [`&.${tabClasses.selected}`]: {
          color: brand[500],
          fontWeight: 500,
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
        borderRadius: 0,
      }),
    },
  },
  MuiStepIcon: {
    styleOverrides: {
      root: () => ({
        color: 'transparent',
        border: `1px solid ${tesla.paleSilver}`,
        width: 12,
        height: 12,
        borderRadius: '50%',
        '& text': {
          display: 'none',
        },
        '&.Mui-active': {
          border: 'none',
          color: brand[500],
        },
        '&.Mui-completed': {
          border: 'none',
          color: brand[500],
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
