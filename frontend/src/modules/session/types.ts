export type SessionUser = {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
};

export type LoginRequest = {
  email: string;
  password: string;
  remember_me?: boolean;
};

export type LoginResponse = {
  access_token?: string;
};

export type SignUpRequest = {
  full_name: string;
  email: string;
  password: string;
};
