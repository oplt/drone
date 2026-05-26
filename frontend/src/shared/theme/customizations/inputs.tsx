/* eslint-disable import/prefer-default-export */
import { alpha } from '@mui/material/styles';
import type { Components } from "@mui/material/styles";
import type { Theme } from "@mui/material/styles";
import { outlinedInputClasses } from '@mui/material/OutlinedInput';
import { svgIconClasses } from '@mui/material/SvgIcon';
import { toggleButtonGroupClasses } from '@mui/material/ToggleButtonGroup';
import { toggleButtonClasses } from '@mui/material/ToggleButton';
import CheckBoxOutlineBlankRoundedIcon from '@mui/icons-material/CheckBoxOutlineBlankRounded';
import CheckRoundedIcon from '@mui/icons-material/CheckRounded';
import RemoveRoundedIcon from '@mui/icons-material/RemoveRounded';
import { brand } from '../themePrimitives';

/* eslint-disable import/prefer-default-export */
export const inputsCustomizations: Components<Theme> = {
  MuiButtonBase: {
    defaultProps: {
      disableTouchRipple: true,
      disableRipple: true,
    },
    styleOverrides: {
      root: ({ theme }) => ({
        boxSizing: 'border-box',
        transition: 'all 150ms cubic-bezier(0.25, 0.1, 0.25, 1)',
        '&:focus-visible': {
          outline: `1px solid ${(theme.vars || theme).palette.text.primary}`,
          outlineOffset: '2px',
        },
      }),
    },
  },
  MuiButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        boxShadow: 'none',
        borderRadius: 999,
        textTransform: 'uppercase',
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.8125rem',
        fontWeight: 400,
        letterSpacing: '0.06em',
        minHeight: 44,
        variants: [
          {
            props: { size: 'small' },
            style: {
              height: '2.25rem',
              padding: '8px 20px',
            },
          },
          {
            props: { size: 'medium' },
            style: {
              height: '2.75rem',
              padding: '8px 24px',
            },
          },
          {
            props: { size: 'large' },
            style: {
              height: '3.25rem',
              padding: '12px 24px',
            },
          },
          {
            props: { color: 'primary', variant: 'contained' },
            style: {
              color: '#000000',
              backgroundColor: '#FFFFFF',
              border: 'none',
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: '#E8E8E8',
                boxShadow: 'none',
              },
              '&:active': {
                backgroundColor: '#CCCCCC',
              },
              ...theme.applyStyles('dark', {
                color: '#000000',
                backgroundColor: '#FFFFFF',
                '&:hover': {
                  backgroundColor: '#E8E8E8',
                },
                '&:active': {
                  backgroundColor: '#CCCCCC',
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'contained' },
            style: {
              color: '#FFFFFF',
              backgroundColor: '#000000',
              border: 'none',
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: '#1A1A1A',
              },
              ...theme.applyStyles('dark', {
                color: '#000000',
                backgroundColor: '#E8E8E8',
                '&:hover': {
                  backgroundColor: '#CCCCCC',
                },
              }),
            },
          },
          {
            props: { variant: 'outlined' },
            style: {
              color: (theme.vars || theme).palette.text.primary,
              border: `1px solid #333333`,
              backgroundColor: 'transparent',
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: alpha('#999999', 0.08),
                borderColor: (theme.vars || theme).palette.text.primary,
              },
              ...theme.applyStyles('dark', {
                borderColor: '#333333',
                '&:hover': {
                  borderColor: '#E8E8E8',
                  backgroundColor: alpha('#999999', 0.08),
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'outlined' },
            style: {
              color: (theme.vars || theme).palette.text.secondary,
              border: `1px solid #333333`,
              backgroundColor: 'transparent',
              boxShadow: 'none',
              '&:hover': {
                borderColor: (theme.vars || theme).palette.text.primary,
                color: (theme.vars || theme).palette.text.primary,
              },
            },
          },
          {
            props: { variant: 'text' },
            style: {
              color: (theme.vars || theme).palette.text.secondary,
              '&:hover': {
                backgroundColor: alpha('#999999', 0.08),
                color: (theme.vars || theme).palette.text.primary,
              },
            },
          },
          {
            props: { color: 'error' },
            style: {
              color: brand[500],
              borderColor: brand[500],
              '&:hover': {
                backgroundColor: alpha(brand[500], 0.08),
              },
            },
          },
        ],
      }),
    },
  },
  MuiIconButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        boxShadow: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        textTransform: 'none',
        color: (theme.vars || theme).palette.text.secondary,
        border: '1px solid',
        borderColor: '#333333',
        backgroundColor: 'transparent',
        '&:hover': {
          backgroundColor: alpha('#999999', 0.08),
          borderColor: (theme.vars || theme).palette.text.primary,
          color: (theme.vars || theme).palette.text.primary,
        },
        ...theme.applyStyles('dark', {
          borderColor: '#333333',
          '&:hover': {
            borderColor: '#E8E8E8',
            backgroundColor: alpha('#999999', 0.08),
          },
        }),
        variants: [
          {
            props: { size: 'small' },
            style: {
              width: '2.25rem',
              height: '2.25rem',
              padding: '0.25rem',
              [`& .${svgIconClasses.root}`]: { fontSize: '1rem' },
            },
          },
          {
            props: { size: 'medium' },
            style: {
              width: '2.5rem',
              height: '2.5rem',
            },
          },
        ],
      }),
    },
  },
  MuiToggleButtonGroup: {
    styleOverrides: {
      root: ({ theme }) => ({
        borderRadius: 999,
        boxShadow: 'none',
        border: `1px solid #333333`,
        ...theme.applyStyles('dark', {
          border: `1px solid #333333`,
        }),
        [`& .${toggleButtonGroupClasses.selected}`]: {
          color: (theme.vars || theme).palette.text.primary,
        },
      }),
    },
  },
  MuiToggleButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        padding: '8px 16px',
        textTransform: 'uppercase',
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.6875rem',
        letterSpacing: '0.06em',
        borderRadius: 999,
        fontWeight: 400,
        color: (theme.vars || theme).palette.text.secondary,
        [`&.${toggleButtonClasses.selected}`]: {
          backgroundColor: (theme.vars || theme).palette.text.primary,
          color: (theme.vars || theme).palette.background.default,
        },
      }),
    },
  },
  MuiCheckbox: {
    defaultProps: {
      disableRipple: true,
      icon: (
        <CheckBoxOutlineBlankRoundedIcon sx={{ color: 'hsla(210, 0%, 0%, 0.0)' }} />
      ),
      checkedIcon: <CheckRoundedIcon sx={{ height: 14, width: 14 }} />,
      indeterminateIcon: <RemoveRoundedIcon sx={{ height: 14, width: 14 }} />,
    },
    styleOverrides: {
      root: ({ theme }) => ({
        margin: 10,
        height: 16,
        width: 16,
        borderRadius: 4,
        border: `1px solid #333333`,
        backgroundColor: 'transparent',
        transition: 'border-color 150ms cubic-bezier(0.25, 0.1, 0.25, 1)',
        '&:hover': {
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        '&.Mui-checked': {
          color: '#000000',
          backgroundColor: '#FFFFFF',
          borderColor: '#FFFFFF',
          boxShadow: 'none',
          '&:hover': {
            backgroundColor: '#E8E8E8',
          },
        },
        ...theme.applyStyles('dark', {
          borderColor: '#333333',
          '&:hover': {
            borderColor: '#E8E8E8',
          },
          '&.Mui-checked': {
            color: '#000000',
            backgroundColor: '#FFFFFF',
            borderColor: '#FFFFFF',
          },
        }),
      }),
    },
  },
  MuiInputBase: {
    styleOverrides: {
      root: {
        border: 'none',
      },
      input: {
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        '&::placeholder': {
          opacity: 0.5,
          color: '#999999',
        },
      },
    },
  },
  MuiOutlinedInput: {
    styleOverrides: {
      input: {
        padding: 0,
      },
      root: ({ theme }) => ({
        padding: '8px 12px',
        color: (theme.vars || theme).palette.text.primary,
        borderRadius: 8,
        border: `1px solid #333333`,
        backgroundColor: 'transparent',
        transition: 'border-color 150ms cubic-bezier(0.25, 0.1, 0.25, 1)',
        '&:hover': {
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        [`&.${outlinedInputClasses.focused}`]: {
          outline: 'none',
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        ...theme.applyStyles('dark', {
          borderColor: '#333333',
          '&:hover': {
            borderColor: '#E8E8E8',
          },
          [`&.${outlinedInputClasses.focused}`]: {
            borderColor: '#E8E8E8',
          },
        }),
        variants: [
          {
            props: { size: 'small' },
            style: { height: '2.25rem' },
          },
          {
            props: { size: 'medium' },
            style: { height: '2.5rem' },
          },
        ],
      }),
      notchedOutline: {
        border: 'none',
      },
    },
  },
  MuiInputAdornment: {
    styleOverrides: {
      root: ({ theme }) => ({
        color: (theme.vars || theme).palette.text.secondary,
      }),
    },
  },
  MuiFormLabel: {
    styleOverrides: {
      root: ({ theme }) => ({
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.6875rem',
        fontWeight: 400,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        color: (theme.vars || theme).palette.text.secondary,
        marginBottom: 8,
      }),
    },
  },
  MuiFilledInput: {
    styleOverrides: {
      root: ({ theme }) => ({
        overflow: 'hidden',
        borderRadius: 8,
        border: `1px solid #333333`,
        backgroundColor: 'transparent',
        transition: 'border-color 150ms cubic-bezier(0.25, 0.1, 0.25, 1)',
        '&:before, &:after': {
          display: 'none',
        },
        '&:hover': {
          backgroundColor: alpha('#999999', 0.04),
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        '&.Mui-focused': {
          backgroundColor: 'transparent',
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        '&.Mui-error': {
          borderColor: brand[500],
        },
        ...theme.applyStyles('dark', {
          borderColor: '#333333',
          backgroundColor: 'transparent',
          '&:hover': {
            backgroundColor: alpha('#999999', 0.04),
            borderColor: '#E8E8E8',
          },
          '&.Mui-focused': {
            backgroundColor: 'transparent',
            borderColor: '#E8E8E8',
          },
        }),
      }),
      input: {
        paddingTop: 24,
        paddingBottom: 14,
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
      },
    },
  },
  MuiFormHelperText: {
    styleOverrides: {
      root: {
        marginLeft: 0,
        marginRight: 0,
        fontFamily: '"Space Mono", "JetBrains Mono", monospace',
        fontSize: '0.6875rem',
      },
    },
  },
};
