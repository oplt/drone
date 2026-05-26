export type MissionTemplate = {
  id: number;
  name: string;
  slug: string;
  mission_type: string;
  schedule_cron: string | null;
  is_active: boolean;
  created_at: string;
};
