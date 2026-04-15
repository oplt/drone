import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Select from '@mui/material/Select';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import ScheduleRoundedIcon from '@mui/icons-material/ScheduleRounded';
import Header from '../../../components/dashboard/Header';
import PageLayout, { PageSection } from '../../../components/dashboard/PageLayout';
import { apiRequest } from '../../../utils/api';

interface MissionTemplate {
  id: number;
  name: string;
  slug: string;
  mission_type: string;
  schedule_cron: string | null;
  is_active: boolean;
  created_at: string;
}

const MISSION_TYPES = [
  'grid',
  'waypoints',
  'photogrammetry',
  'private_patrol',
  'warehouse_scan',
  'warehouse_exploration',
];

async function fetchTemplates(): Promise<MissionTemplate[]> {
  const data = await apiRequest<{ items: MissionTemplate[] } | MissionTemplate[]>('/tasks/templates');
  return Array.isArray(data) ? data : (data as any).items ?? [];
}

async function createTemplate(payload: {
  name: string;
  mission_type: string;
  schedule_cron: string | null;
}): Promise<MissionTemplate> {
  return apiRequest<MissionTemplate>('/tasks/templates', {
    method: 'POST',
    body: JSON.stringify({ ...payload, config: {}, preflight_profile: {} }),
  });
}

async function triggerTemplate(id: number): Promise<{ run_id: number }> {
  return apiRequest<{ run_id: number }>(`/tasks/templates/${id}/trigger`, { method: 'POST' });
}

async function toggleTemplate(id: number, is_active: boolean): Promise<void> {
  await apiRequest(`/tasks/templates/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active }),
  });
}

function CreateTemplateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [missionType, setMissionType] = useState('grid');
  const [cron, setCron] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError('');
    try {
      await createTemplate({
        name: name.trim(),
        mission_type: missionType,
        schedule_cron: cron.trim() || null,
      });
      onCreated();
      onClose();
      setName('');
      setCron('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New Mission Template</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Template Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            fullWidth
            autoFocus
          />
          <Select
            value={missionType}
            onChange={(e) => setMissionType(e.target.value)}
            fullWidth
            displayEmpty
          >
            {MISSION_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </MenuItem>
            ))}
          </Select>
          <TextField
            label="Schedule (cron expression, optional)"
            placeholder="e.g. 0 6 * * 1 — every Monday at 06:00"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            fullWidth
            helperText="Leave blank for manual-only templates"
          />
          {error && <Typography color="error" variant="body2">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit} variant="contained" disabled={saving || !name.trim()}>
          {saving ? 'Creating…' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function TemplateRow({ template, onRefresh }: { template: MissionTemplate; onRefresh: () => void }) {
  const [triggering, setTriggering] = useState(false);
  const [toggling, setToggling] = useState(false);

  const handleTrigger = async () => {
    setTriggering(true);
    try {
      await triggerTemplate(template.id);
      onRefresh();
    } finally {
      setTriggering(false);
    }
  };

  const handleToggle = async () => {
    setToggling(true);
    try {
      await toggleTemplate(template.id, !template.is_active);
      onRefresh();
    } finally {
      setToggling(false);
    }
  };

  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 3, display: 'flex', alignItems: 'center', gap: 2 }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body1" fontWeight={600} noWrap>
            {template.name}
          </Typography>
          <Chip
            label={template.mission_type.replace(/_/g, ' ')}
            size="small"
            variant="outlined"
          />
          {!template.is_active && (
            <Chip label="Inactive" size="small" color="default" />
          )}
          {template.schedule_cron && (
            <Tooltip title={`Scheduled: ${template.schedule_cron}`}>
              <ScheduleRoundedIcon fontSize="small" color="action" />
            </Tooltip>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {template.schedule_cron ? `cron: ${template.schedule_cron}` : 'Manual only'} ·{' '}
          Created {new Date(template.created_at).toLocaleDateString()}
        </Typography>
      </Box>

      <Switch
        checked={template.is_active}
        onChange={handleToggle}
        disabled={toggling}
        size="small"
      />

      <Tooltip title="Run now">
        <span>
          <IconButton
            onClick={handleTrigger}
            disabled={triggering || !template.is_active}
            color="primary"
            size="small"
          >
            <PlayArrowRoundedIcon />
          </IconButton>
        </span>
      </Tooltip>
    </Paper>
  );
}

export default function TemplatesPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: fetchTemplates,
    refetchInterval: 30000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['templates'] });

  return (
    <PageLayout>
      <Header
        title="Mission Templates"
        subtitle="Save mission configurations for one-click rerun and scheduled dispatch"
        actions={
          <Button
            variant="contained"
            startIcon={<AddRoundedIcon />}
            onClick={() => setCreateOpen(true)}
            size="small"
          >
            New Template
          </Button>
        }
      />

      <PageSection>
        {isLoading && (
          <Typography color="text.secondary">Loading templates…</Typography>
        )}
        {!isLoading && templates.length === 0 && (
          <Paper
            variant="outlined"
            sx={{ p: 4, borderRadius: 3, textAlign: 'center' }}
          >
            <Typography color="text.secondary">
              No templates yet. Create one to save a mission configuration for reuse.
            </Typography>
          </Paper>
        )}
        <Stack spacing={1.5}>
          {templates.map((t) => (
            <TemplateRow key={t.id} template={t} onRefresh={refresh} />
          ))}
        </Stack>
      </PageSection>

      <CreateTemplateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={refresh}
      />
    </PageLayout>
  );
}
