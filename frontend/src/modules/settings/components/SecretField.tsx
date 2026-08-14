import { useState, type ComponentProps } from "react";
import { IconButton, InputAdornment, TextField } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";

export function SecretField(props: ComponentProps<typeof TextField>) {
  const [show, setShow] = useState(false);
  return (
    <TextField
      variant="filled"
      {...props}
      type={show ? "text" : "password"}
      InputProps={{
        endAdornment: (
          <InputAdornment position="end">
            <IconButton
              onClick={() => setShow((value) => !value)}
              onMouseDown={(event) => event.preventDefault()}
              edge="end"
              size="small"
              aria-label={show ? "Hide value" : "Show value"}
            >
              {show ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
            </IconButton>
          </InputAdornment>
        ),
      }}
    />
  );
}
