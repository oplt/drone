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
import { gray, brand } from '../themePrimitives';

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
        transition: 'all 100ms ease-in',
        '&:focus-visible': {
          outline: `1px solid ${brand[500]}`,
          outlineOffset: '2px',
        },
      }),
    },
  },
  MuiButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        boxShadow: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        textTransform: 'none',
        fontWeight: 600,
        variants: [
          {
            props: { size: 'small' },
            style: {
              height: '2.25rem',
              padding: '8px 12px',
            },
          },
          {
            props: { size: 'medium' },
            style: {
              height: '2.75rem',
              padding: '8px 16px',
            },
          },
          {
            props: { size: 'large' },
            style: {
              height: '3.5rem',
              padding: '20px 24px',
              borderRadius: 8,
            },
          },
          {
            props: { color: 'primary', variant: 'contained' },
            style: {
              color: gray[50],
              backgroundColor: brand[500],
              border: `1px solid ${brand[500]}`,
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: brand[600],
                boxShadow: 'none',
              },
              '&:active': {
                backgroundColor: brand[700],
              },
              ...theme.applyStyles('dark', {
                color: gray[50],
                backgroundColor: brand[500],
                border: `1px solid ${brand[500]}`,
                '&:hover': {
                  backgroundColor: brand[600],
                },
                '&:active': {
                  backgroundColor: brand[700],
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'contained' },
            style: {
              color: gray[50],
              backgroundColor: gray[800],
              border: `1px solid ${gray[800]}`,
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: gray[300],
                color: gray[800],
                borderColor: gray[300],
              },
              '&:active': {
                backgroundColor: gray[200],
              },
              ...theme.applyStyles('dark', {
                color: gray[50],
                backgroundColor: gray[700],
                borderColor: gray[700],
                '&:hover': {
                  backgroundColor: gray[600],
                },
              }),
            },
          },
          {
            props: { variant: 'outlined' },
            style: {
              color: gray[600],
              border: `1px solid ${gray[300]}`,
              backgroundColor: gray[200],
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: gray[300],
                borderColor: gray[300],
                color: gray[800],
              },
              '&:active': {
                backgroundColor: gray[300],
              },
              ...theme.applyStyles('dark', {
                color: gray[300],
                backgroundColor: alpha(gray[700], 0.3),
                borderColor: alpha(gray[300], 0.2),
                '&:hover': {
                  backgroundColor: alpha(gray[600], 0.4),
                  borderColor: alpha(gray[300], 0.3),
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'outlined' },
            style: {
              color: gray[600],
              border: `1px solid ${gray[300]}`,
              backgroundColor: gray[50],
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: gray[200],
                borderColor: gray[300],
              },
              '&:active': {
                backgroundColor: gray[200],
              },
              ...theme.applyStyles('dark', {
                color: gray[300],
                borderColor: alpha(gray[300], 0.15),
                backgroundColor: 'transparent',
                '&:hover': {
                  borderColor: alpha(gray[300], 0.25),
                  backgroundColor: alpha(gray[300], 0.06),
                },
              }),
            },
          },
          {
            props: { variant: 'text' },
            style: {
              color: gray[600],
              '&:hover': {
                backgroundColor: gray[200],
              },
              '&:active': {
                backgroundColor: gray[300],
              },
              ...theme.applyStyles('dark', {
                color: gray[300],
                '&:hover': {
                  backgroundColor: alpha(gray[300], 0.08),
                },
                '&:active': {
                  backgroundColor: alpha(gray[300], 0.12),
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'text' },
            style: {
              color: brand[600],
              '&:hover': {
                backgroundColor: alpha(brand[100], 0.5),
              },
              '&:active': {
                backgroundColor: alpha(brand[200], 0.7),
              },
              ...theme.applyStyles('dark', {
                color: brand[300],
                '&:hover': {
                  backgroundColor: alpha(brand[900], 0.3),
                },
              }),
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
        fontWeight: theme.typography.fontWeightMedium,
        letterSpacing: 0,
        color: (theme.vars || theme).palette.text.primary,
        border: '1px solid',
        borderColor: gray[300],
        backgroundColor: 'transparent',
        '&:hover': {
          backgroundColor: gray[200],
          borderColor: gray[300],
        },
        '&:active': {
          backgroundColor: gray[300],
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(gray[300], 0.15),
          '&:hover': {
            backgroundColor: alpha(gray[300], 0.08),
            borderColor: alpha(gray[300], 0.2),
          },
          '&:active': {
            backgroundColor: alpha(gray[300], 0.12),
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
        borderRadius: (theme.vars || theme).shape.borderRadius,
        boxShadow: 'none',
        border: `1px solid ${gray[300]}`,
        [`& .${toggleButtonGroupClasses.selected}`]: {
          color: brand[500],
        },
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(gray[300], 0.15)}`,
          [`& .${toggleButtonGroupClasses.selected}`]: {
            color: brand[400],
          },
        }),
      }),
    },
  },
  MuiToggleButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        padding: '8px 16px',
        textTransform: 'none',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        fontWeight: 500,
        color: gray[600],
        ...theme.applyStyles('dark', {
          color: gray[400],
          [`&.${toggleButtonClasses.selected}`]: {
            color: brand[400],
          },
        }),
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
        border: `1px solid ${gray[300]}`,
        backgroundColor: gray[50],
        transition: 'border-color, background-color, 120ms ease-in',
        '&:hover': {
          borderColor: brand[400],
        },
        '&.Mui-focusVisible': {
          outline: `1px solid ${brand[500]}`,
          outlineOffset: '2px',
          borderColor: brand[500],
        },
        '&.Mui-checked': {
          color: gray[50],
          backgroundColor: brand[500],
          borderColor: brand[500],
          boxShadow: 'none',
          '&:hover': {
            backgroundColor: brand[600],
          },
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(gray[300], 0.2),
          backgroundColor: 'transparent',
          '&:hover': {
            borderColor: brand[400],
          },
          '&.Mui-focusVisible': {
            borderColor: brand[400],
            outline: `1px solid ${brand[500]}`,
            outlineOffset: '2px',
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
        '&::placeholder': {
          opacity: 0.7,
          color: gray[500],
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
        borderRadius: (theme.vars || theme).shape.borderRadius,
        border: `1px solid ${gray[300]}`,
        backgroundColor: gray[50],
        transition: 'border-color 120ms ease-in',
        '&:hover': {
          borderColor: gray[400],
        },
        [`&.${outlinedInputClasses.focused}`]: {
          outline: 'none',
          borderColor: brand[500],
        },
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(gray[300], 0.15)}`,
          backgroundColor: alpha(gray[800], 0.5),
          '&:hover': {
            borderColor: alpha(gray[300], 0.25),
          },
          [`&.${outlinedInputClasses.focused}`]: {
            borderColor: brand[500],
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
        color: (theme.vars || theme).palette.grey[500],
        ...theme.applyStyles('dark', {
          color: (theme.vars || theme).palette.grey[400],
        }),
      }),
    },
  },
  MuiFormLabel: {
    styleOverrides: {
      root: ({ theme }) => ({
        typography: theme.typography.caption,
        marginBottom: 8,
      }),
    },
  },
  MuiFilledInput: {
    styleOverrides: {
      root: ({ theme }) => ({
        overflow: 'hidden',
        borderRadius: (theme.vars || theme).shape.borderRadius,
        border: `1px solid ${gray[300]}`,
        backgroundColor: gray[50],
        transition: 'border-color 140ms ease, background-color 140ms ease',
        '&:before, &:after': {
          display: 'none',
        },
        '&:hover': {
          backgroundColor: gray[100],
          borderColor: gray[400],
        },
        '&.Mui-focused': {
          backgroundColor: gray[50],
          borderColor: brand[500],
        },
        '&.Mui-error': {
          borderColor: theme.palette.error.main,
        },
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(gray[300], 0.15)}`,
          backgroundColor: alpha(gray[800], 0.5),
          '&:hover': {
            backgroundColor: alpha(gray[800], 0.7),
            borderColor: alpha(gray[300], 0.2),
          },
          '&.Mui-focused': {
            backgroundColor: alpha(gray[800], 0.85),
            borderColor: brand[500],
          },
        }),
      }),
      input: {
        paddingTop: 24,
        paddingBottom: 14,
      },
    },
  },
  MuiFormHelperText: {
    styleOverrides: {
      root: {
        marginLeft: 0,
        marginRight: 0,
      },
    },
  },
};
