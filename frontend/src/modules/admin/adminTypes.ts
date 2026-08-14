export const ADMIN_ROLES = [
  "admin",
  "org_admin",
  "ops_manager",
  "pilot",
  "viewer",
  "operator",
] as const;

export const ADMIN_TABS = [
  "Users",
  "Organizations",
  "Mapping Jobs",
  "Export Jobs",
  "Worker Health",
  "Diagnostics",
] as const;

export type AdminUser = {
  id: number;
  email: string;
  role: string;
  org_id: number | null;
  full_name: string | null;
  created_at: string;
};

export type AdminUsersResponse = {
  users: AdminUser[];
};

export type AdminOrganization = {
  id: number;
  name: string;
  slug: string;
  user_count: number;
  created_at: string;
};

export type AdminOrganizationsResponse = {
  organizations: AdminOrganization[];
};

export type AdminMappingJob = {
  id: number;
  field_id: number;
  status: string;
  progress: number;
  created_at: string;
  finished_at: string | null;
};

export type AdminMappingJobsResponse = {
  jobs: AdminMappingJob[];
};

export type AdminExportJob = {
  id: number;
  org_id: number | null;
  flight_id: string;
  status: string;
  download_url: string | null;
  created_at: string;
};

export type AdminExportJobsResponse = {
  jobs: AdminExportJob[];
};

export type AdminWorkerHealthResponse = {
  error?: string;
  workers?: string[];
  active_tasks?: Record<string, number>;
  reserved_tasks?: Record<string, number>;
  total_active?: number;
};
