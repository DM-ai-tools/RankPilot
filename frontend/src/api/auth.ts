import { apiPostPublic } from "./client";

export type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export async function loginRequest(username: string, password: string): Promise<LoginResponse> {
  return apiPostPublic<LoginResponse, { username: string; password: string }>("/api/v1/auth/login", {
    username,
    password,
  });
}
