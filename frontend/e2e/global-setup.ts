import { API_URL } from './helpers';

export default async function globalSetup(): Promise<void> {
  const url = `${API_URL}/health/ready`;
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new Error(
      `API ${API_URL} is unreachable. From repo root run: docker compose up -d postgres api`,
    );
  }
  if (!response.ok) {
    throw new Error(
      `API ${url} returned ${response.status}. Start postgres (host 5434) and api (8000); never SQLite.`,
    );
  }
}
