import Chip from '@mui/material/Chip';
import type { GridColDef, GridRenderCellParams } from '@mui/x-data-grid';

export const columns: GridColDef[] = [
  { field: 'plan', headerName: 'Field Plan', flex: 1.2, minWidth: 180 },
  {
    field: 'status',
    headerName: 'Status',
    flex: 0.6,
    minWidth: 100,
    renderCell: (params: GridRenderCellParams) => {
      const label = typeof params.value === 'string' ? params.value : 'Unknown';
      const value = label.toLowerCase();
      const color =
        value.includes('progress') || value.includes('active')
          ? 'success'
          : value.includes('fail')
            ? 'error'
            : 'default';
      return (
        <Chip
          label={label}
          color={color}
          size="small"
          variant="outlined"
        />
      );
    },
  },
  {
    field: 'duration',
    headerName: 'Duration',
    headerAlign: 'right',
    align: 'right',
    flex: 0.7,
    minWidth: 110,
  },
  {
    field: 'distance',
    headerName: 'Distance',
    headerAlign: 'right',
    align: 'right',
    flex: 0.7,
    minWidth: 110,
  },
  {
    field: 'telemetry_points',
    headerName: 'Telemetry',
    headerAlign: 'right',
    align: 'right',
    flex: 0.7,
    minWidth: 120,
  },
  {
    field: 'started_at',
    headerName: 'Started',
    headerAlign: 'right',
    align: 'right',
    flex: 0.9,
    minWidth: 140,
  },
];
