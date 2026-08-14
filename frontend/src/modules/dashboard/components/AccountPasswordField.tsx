import { useState, type ComponentProps, type ReactNode } from "react";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import TextField from "@mui/material/TextField";
import VisibilityRoundedIcon from "@mui/icons-material/VisibilityRounded";
import VisibilityOffRoundedIcon from "@mui/icons-material/VisibilityOffRounded";

export function AccountPasswordField({
  label,
  value,
  onChange,
  disabled,
  helperText,
  error,
  inputLabelProps,
}: {
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  helperText?: string;
  error?: boolean;
  inputLabelProps?: ComponentProps<typeof TextField>["InputLabelProps"];
}) {
  const [show, setShow] = useState(false);
  return (
    <TextField
      fullWidth
      label={label}
      type={show ? "text" : "password"}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      helperText={helperText}
      error={error}
      InputLabelProps={inputLabelProps}
      variant="filled"
      slotProps={{
        input: {
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={() => setShow((current) => !current)}
                edge="end"
                tabIndex={-1}
                aria-label={show ? "Hide password" : "Show password"}
              >
                {show ? <VisibilityOffRoundedIcon /> : <VisibilityRoundedIcon />}
              </IconButton>
            </InputAdornment>
          ),
        },
      }}
    />
  );
}
