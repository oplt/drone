import * as React from 'react';
import dayjs, { Dayjs } from 'dayjs';
import { useForkRef } from '@mui/material/utils';
import { IconButton, Tooltip } from '@mui/material';
import CalendarTodayRoundedIcon from '@mui/icons-material/CalendarTodayRounded';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import type { DatePickerFieldProps } from "@mui/x-date-pickers/DatePicker";
import {
  useParsedFormat,
  usePickerContext,
  useSplitFieldProps,
} from '@mui/x-date-pickers';

interface ButtonFieldProps extends DatePickerFieldProps {}

function ButtonField(props: ButtonFieldProps) {
  const { forwardedProps } = useSplitFieldProps(props, 'date');
  const pickerContext = usePickerContext();
  const handleRef = useForkRef(pickerContext.triggerRef, pickerContext.rootRef);
  const parsedFormat = useParsedFormat();
  const valueStr =
    pickerContext.value == null
      ? parsedFormat
      : pickerContext.value.format(pickerContext.fieldFormat);
  const label = String(pickerContext.label ?? valueStr);
  const {
    inputRef,
    slotProps,
    onClick: forwardedOnClick,
    ...buttonProps
  } = forwardedProps as Record<string, unknown>;

  return (
    <Tooltip title={label}>
      <span>
        <IconButton
          {...buttonProps}
          ref={handleRef}
          size="small"
          aria-label={label}
          onClick={(event) => {
            if (typeof forwardedOnClick === 'function') {
              forwardedOnClick(event);
            }
            pickerContext.setOpen((prev) => !prev);
          }}
        >
          <CalendarTodayRoundedIcon fontSize="small" />
        </IconButton>
      </span>
    </Tooltip>
  );
}

export default function CustomDatePicker() {
  const [value, setValue] = React.useState<Dayjs | null>(dayjs());

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <DatePicker
        value={value}
        label={value == null ? 'Select date' : value.format('MMM DD, YYYY')}
        onChange={(newValue) => setValue(newValue)}
        slots={{ field: ButtonField }}
        slotProps={{
          nextIconButton: { size: 'small' },
          previousIconButton: { size: 'small' },
        }}
        views={['day', 'month', 'year']}
      />
    </LocalizationProvider>
  );
}
