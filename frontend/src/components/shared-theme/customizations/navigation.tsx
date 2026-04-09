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
import { gray, brand } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const navigationCustomizations: Components<Theme> = {
  MuiMenuItem: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: (theme.vars || theme).shape.borderRadius,
        padding: '6px 8px',
        [`&.${menuItemClasses.focusVisible}`]: {
          backgroundColor: 'transparent',
        },
        [`&.${menuItemClasses.selected}`]: {
          [`&.${menuItemClasses.focusVisible}`]: {
            backgroundColor: alpha(theme.palette.action.selected, 0.3),
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
        borderRadius: (theme.vars || theme).shape.borderRadius,
        border: `1px solid ${gray[300]}`,
        backgroundImage: 'none',
        background: gray[50],
        boxShadow: 'none',
        [`& .${buttonBaseClasses.root}`]: {
          '&.Mui-selected': {
            backgroundColor: alpha(theme.palette.action.selected, 0.3),
          },
        },
        ...theme.applyStyles('dark', {
          background: '#211916',
          border: `1px solid ${alpha(gray[300], 0.12)}`,
          boxShadow: 'none',
        }),
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
        borderRadius: (theme.vars || theme).shape.borderRadius,
        border: `1px solid ${gray[300]}`,
        backgroundColor: gray[50],
        boxShadow: 'none',
        '&:hover': {
          borderColor: gray[400],
          backgroundColor: gray[50],
          boxShadow: 'none',
        },
        [`&.${selectClasses.focused}`]: {
          outlineOffset: 0,
          borderColor: brand[500],
        },
        '&:before, &:after': {
          display: 'none',
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(gray[300], 0.15),
          backgroundColor: alpha(gray[800], 0.5),
          boxShadow: 'none',
          '&:hover': {
            borderColor: alpha(gray[300], 0.25),
            backgroundColor: alpha(gray[800], 0.6),
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
      }),
      select: ({ theme }) => ({
        display: 'flex',
        alignItems: 'center',
        ...theme.applyStyles('dark', {
          display: 'flex',
          alignItems: 'center',
          '&:focus-visible': {
            backgroundColor: 'transparent',
          },
        }),
      }),
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
          backgroundColor: gray[300],
          opacity: 0.6,
          transition: 'width 0.3s ease, opacity 0.3s ease',
        },
        '&:hover::before': {
          width: 0,
        },
        '&:focus-visible': {
          outline: `1px solid ${brand[500]}`,
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
        borderRight: `1px solid ${gray[300]}`,
        ...theme.applyStyles('dark', {
          borderRight: `1px solid ${alpha(gray[300], 0.12)}`,
        }),
      }),
    },
  },
  MuiPaginationItem: {
    styleOverrides: {
      root: ({ theme }) => ({
        '&.Mui-selected': {
          color: gray[50],
          backgroundColor: gray[800],
        },
        ...theme.applyStyles('dark', {
          '&.Mui-selected': {
            color: gray[800],
            backgroundColor: gray[50],
          },
        }),
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
        textTransform: 'none',
        minWidth: 'fit-content',
        minHeight: 'fit-content',
        fontWeight: 500,
        fontSize: '1rem',
        color: (theme.vars || theme).palette.text.primary,
        borderRadius: 0,
        border: 'none',
        boxShadow: 'none',
        // Hover: sand inset underline
        ':hover': {
          color: (theme.vars || theme).palette.text.primary,
          backgroundColor: 'transparent',
          boxShadow: `rgb(197, 192, 177) 0px -4px 0px 0px inset`,
        },
        // Active: orange inset underline
        [`&.${tabClasses.selected}`]: {
          color: gray[800],
          fontWeight: 600,
          boxShadow: `rgb(255, 79, 0) 0px -4px 0px 0px inset`,
        },
        ...theme.applyStyles('dark', {
          color: gray[300],
          ':hover': {
            color: gray[50],
            backgroundColor: 'transparent',
            boxShadow: `${alpha(gray[300], 0.3)} 0px -4px 0px 0px inset`,
          },
          [`&.${tabClasses.selected}`]: {
            color: gray[50],
            boxShadow: `rgb(255, 79, 0) 0px -4px 0px 0px inset`,
          },
        }),
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
        border: `1px solid ${gray[400]}`,
        width: 12,
        height: 12,
        borderRadius: '50%',
        '& text': {
          display: 'none',
        },
        '&.Mui-active': {
          border: 'none',
          color: (theme.vars || theme).palette.primary.main,
        },
        '&.Mui-completed': {
          border: 'none',
          color: (theme.vars || theme).palette.success.main,
        },
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(gray[300], 0.2)}`,
          '&.Mui-active': {
            border: 'none',
            color: (theme.vars || theme).palette.primary.light,
          },
          '&.Mui-completed': {
            border: 'none',
            color: (theme.vars || theme).palette.success.light,
          },
        }),
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
