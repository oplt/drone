export const agricultureAccessibilityStyles = {
  ".agriculture-surface :focus-visible": {
    outline: "3px solid #174ea6",
    outlineOffset: "3px",
    borderRadius: "4px",
  },
  ".agriculture-surface [role='status']": { minHeight: "24px" },
  "@media (pointer: coarse), (max-width: 767px)": {
    ".agriculture-surface button, .agriculture-surface a, .agriculture-surface [role='button'], .agriculture-surface [role='combobox']":
      { minHeight: "44px", minWidth: "44px" },
    ".agriculture-surface input[type='range']": { minHeight: "44px" },
  },
  "@media (prefers-reduced-motion: reduce)": {
    ".agriculture-surface, .agriculture-surface *, .agriculture-surface *::before, .agriculture-surface *::after":
      {
        animationDuration: "0.01ms !important",
        animationIterationCount: "1 !important",
        scrollBehavior: "auto !important",
        transitionDuration: "0.01ms !important",
      },
  },
} as const;
