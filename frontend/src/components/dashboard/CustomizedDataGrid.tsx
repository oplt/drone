import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { DataGrid, type GridRowsProp } from '@mui/x-data-grid';
import { columns } from './gridData';

type CustomizedDataGridProps = {
  rows?: GridRowsProp;
  loading?: boolean;
};

function EmptyRowsOverlay() {
  return (
    <Stack
      sx={{ height: '100%', minHeight: 220, alignItems: 'center', justifyContent: 'center', px: 3 }}
      spacing={1}
    >
      <Typography variant="h6">No flight records yet</Typography>
      <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center', maxWidth: 320 }}>
        Recent missions, telemetry activity, and route status will appear here once the first runs
        are completed.
      </Typography>
    </Stack>
  );
}

function GridLoadingOverlay() {
  return (
    <Stack spacing={1.5} sx={{ width: '100%', p: 2.5 }}>
      {[0, 1, 2, 3, 4].map((index) => (
        <Skeleton key={index} variant="rounded" height={40} />
      ))}
    </Stack>
  );
}

export default function CustomizedDataGrid({ rows, loading }: CustomizedDataGridProps) {
  return (
    <Box sx={{ minHeight: 440 }}>
      <DataGrid
        checkboxSelection
        rows={rows ?? []}
        loading={loading}
        columns={columns}
        autoHeight
        disableRowSelectionOnClick
        getRowClassName={(params) =>
          params.indexRelativeToCurrentPage % 2 === 0 ? 'even' : 'odd'
        }
        initialState={{
          pagination: { paginationModel: { pageSize: 20 } },
        }}
        pageSizeOptions={[10, 20, 50]}
        disableColumnResize
        density="compact"
        slots={{
          noRowsOverlay: EmptyRowsOverlay,
          loadingOverlay: GridLoadingOverlay,
        }}
        slotProps={{
          filterPanel: {
            filterFormProps: {
              logicOperatorInputProps: {
                variant: 'outlined',
                size: 'small',
              },
              columnInputProps: {
                variant: 'outlined',
                size: 'small',
                sx: { mt: 'auto' },
              },
              operatorInputProps: {
                variant: 'outlined',
                size: 'small',
                sx: { mt: 'auto' },
              },
              valueInputProps: {
                InputComponentProps: {
                  variant: 'outlined',
                  size: 'small',
                },
              },
            },
          },
        }}
        sx={{
          border: 0,
          '--DataGrid-overlayHeight': '220px',
          '& .MuiDataGrid-columnHeaders': {
            borderBottom: '1px solid',
            borderColor: 'divider',
          },
          '& .MuiDataGrid-cell': {
            borderColor: 'divider',
          },
          '& .MuiDataGrid-row:hover': {
            backgroundColor: 'action.hover',
          },
        }}
      />
    </Box>
  );
}
