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
import { brand, fontText, tesla, teslaTransition } from '../themePrimitives';

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
        transition: teslaTransition,
        '&:focus-visible': {
          outline: `2px solid ${(theme.vars || theme).palette.primary.main}`,
          outlineOffset: '2px',
        },
      }),
    },
  },
  MuiButton: {
    styleOverrides: {
      root: ({ theme }) => ({
        boxShadow: 'none',
        borderRadius: 4,
        textTransform: 'none',
        fontFamily: fontText,
        fontSize: '0.875rem',
        fontWeight: 500,
        letterSpacing: 'normal',
        minHeight: 40,
        border: '3px solid transparent',
        transition: teslaTransition,
        variants: [
          {
            props: { size: 'small' },
            style: {
              minHeight: 32,
              padding: '4px 12px',
            },
          },
          {
            props: { size: 'medium' },
            style: {
              minHeight: 40,
              padding: '4px 16px',
            },
          },
          {
            props: { size: 'large' },
            style: {
              minHeight: 48,
              padding: '4px 24px',
            },
          },
          {
            props: { color: 'primary', variant: 'contained' },
            style: {
              color: tesla.white,
              backgroundColor: brand[500],
              boxShadow: 'rgba(0,0,0,0) 0px 0px 0px 2px inset',
              '&:hover': {
                backgroundColor: brand[600],
                boxShadow: 'none',
              },
              '&:active': {
                backgroundColor: brand[700],
              },
              '&:focus-visible': {
                boxShadow: `rgba(0,0,0,0) 0px 0px 0px 2px inset, 0 0 0 2px ${brand[500]}`,
              },
            },
          },
          {
            props: { color: 'secondary', variant: 'contained' },
            style: {
              color: tesla.graphite,
              backgroundColor: tesla.white,
              border: '3px solid transparent',
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: tesla.lightAsh,
              },
              ...theme.applyStyles('dark', {
                color: tesla.carbonDark,
                backgroundColor: tesla.white,
                '&:hover': {
                  backgroundColor: tesla.lightAsh,
                },
              }),
            },
          },
          {
            props: { variant: 'outlined' },
            style: {
              color: (theme.vars || theme).palette.text.primary,
              border: `1px solid ${tesla.paleSilver}`,
              backgroundColor: tesla.white,
              boxShadow: 'none',
              '&:hover': {
                backgroundColor: tesla.lightAsh,
                borderColor: tesla.paleSilver,
              },
              ...theme.applyStyles('dark', {
                color: tesla.white,
                backgroundColor: 'transparent',
                borderColor: alpha(tesla.white, 0.2),
                '&:hover': {
                  backgroundColor: alpha(tesla.white, 0.06),
                },
              }),
            },
          },
          {
            props: { color: 'secondary', variant: 'outlined' },
            style: {
              color: tesla.pewter,
              border: `1px solid ${tesla.paleSilver}`,
              backgroundColor: tesla.white,
              boxShadow: 'none',
              '&:hover': {
                color: tesla.graphite,
                backgroundColor: tesla.lightAsh,
              },
            },
          },
          {
            props: { variant: 'text' },
            style: {
              color: tesla.pewter,
              minHeight: 32,
              padding: '4px 16px',
              '&:hover': {
                backgroundColor: alpha(tesla.carbonDark, 0.04),
                color: tesla.graphite,
                textDecoration: 'underline',
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
        borderRadius: 4,
        textTransform: 'none',
        color: (theme.vars || theme).palette.text.secondary,
        border: 'none',
        backgroundColor: 'transparent',
        transition: teslaTransition,
        '&:hover': {
          backgroundColor: alpha(tesla.carbonDark, 0.04),
          color: (theme.vars || theme).palette.text.primary,
        },
        ...theme.applyStyles('dark', {
          '&:hover': {
            backgroundColor: alpha(tesla.white, 0.06),
          },
        }),
        variants: [
          {
            props: { size: 'small' },
            style: {
              width: '2rem',
              height: '2rem',
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
        borderRadius: 4,
        boxShadow: 'none',
        border: `1px solid ${tesla.cloudGray}`,
        ...theme.applyStyles('dark', {
          border: `1px solid ${alpha(tesla.white, 0.12)}`,
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
        padding: '4px 16px',
        textTransform: 'none',
        fontFamily: fontText,
        fontSize: '0.875rem',
        letterSpacing: 'normal',
        borderRadius: 4,
        fontWeight: 500,
        color: (theme.vars || theme).palette.text.secondary,
        transition: teslaTransition,
        [`&.${toggleButtonClasses.selected}`]: {
          backgroundColor: alpha(brand[500], 0.1),
          color: brand[500],
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
        border: `1px solid ${tesla.paleSilver}`,
        backgroundColor: 'transparent',
        transition: teslaTransition,
        '&:hover': {
          borderColor: (theme.vars || theme).palette.text.primary,
        },
        '&.Mui-checked': {
          color: tesla.white,
          backgroundColor: brand[500],
          borderColor: brand[500],
          boxShadow: 'none',
          '&:hover': {
            backgroundColor: brand[600],
          },
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(tesla.white, 0.2),
          '&.Mui-checked': {
            color: tesla.white,
            backgroundColor: brand[500],
            borderColor: brand[500],
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
        fontFamily: fontText,
        fontSize: '0.875rem',
        '&::placeholder': {
          opacity: 1,
          color: tesla.silverFog,
        },
        '&[type=number]': {
          MozAppearance: 'textfield',
        },
        '&[type=number]::-webkit-outer-spin-button, &[type=number]::-webkit-inner-spin-button':
          {
            WebkitAppearance: 'none',
            margin: 0,
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
        borderRadius: 4,
        border: `1px solid ${tesla.paleSilver}`,
        backgroundColor: 'transparent',
        transition: teslaTransition,
        '&:hover': {
          borderColor: tesla.silverFog,
        },
        [`&.${outlinedInputClasses.focused}`]: {
          outline: 'none',
          borderColor: brand[500],
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(tesla.white, 0.2),
          '&:hover': {
            borderColor: alpha(tesla.white, 0.35),
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
        color: (theme.vars || theme).palette.text.secondary,
      }),
    },
  },
  MuiFormLabel: {
    styleOverrides: {
      root: ({ theme }) => ({
        fontFamily: fontText,
        fontSize: '0.875rem',
        fontWeight: 500,
        letterSpacing: 'normal',
        textTransform: 'none' as const,
        color: (theme.vars || theme).palette.text.secondary,
        marginBottom: 8,
      }),
    },
  },
  MuiFilledInput: {
    styleOverrides: {
      root: ({ theme }) => ({
        overflow: 'hidden',
        borderRadius: 4,
        border: `1px solid ${tesla.paleSilver}`,
        backgroundColor: 'transparent',
        transition: teslaTransition,
        '&:before, &:after': {
          display: 'none',
        },
        '&:hover': {
          backgroundColor: alpha(tesla.carbonDark, 0.02),
          borderColor: tesla.silverFog,
        },
        '&.Mui-focused': {
          backgroundColor: 'transparent',
          borderColor: brand[500],
        },
        '&.Mui-error': {
          borderColor: brand[500],
        },
        ...theme.applyStyles('dark', {
          borderColor: alpha(tesla.white, 0.2),
          '&:hover': {
            backgroundColor: alpha(tesla.white, 0.04),
          },
          '&.Mui-focused': {
            borderColor: brand[500],
          },
        }),
      }),
      input: {
        paddingTop: 24,
        paddingBottom: 14,
        fontFamily: fontText,
      },
    },
  },
  MuiFormHelperText: {
    styleOverrides: {
      root: {
        marginLeft: 0,
        marginRight: 0,
        fontFamily: fontText,
        fontSize: '0.75rem',
      },
    },
  },
};
