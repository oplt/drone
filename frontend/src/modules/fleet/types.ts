export type CertItem = {
  id: number;
  cert_type: string;
  cert_number: string;
  issued_at: string;
  expires_at: string | null;
  issuing_authority: string | null;
  document_url: string | null;
};

export type DeviceItem = {
  id: number;
  device_id: string;
  device_name: string;
  status: string;
  last_inspection_at: string | null;
  next_inspection_due: string | null;
  notes: string | null;
};
