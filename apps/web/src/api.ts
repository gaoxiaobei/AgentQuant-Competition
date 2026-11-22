import type { components } from './api.generated'

type Schema = components['schemas']
export type Catalog = Schema['Catalog']
export type Submission = Schema['Submission']
export type Run = Schema['Run']
export type Result = Schema['EvaluationResult']

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.message ?? (response.status === 422 ? '请检查输入字段' : '请求失败，请重试'))
  }
  return response.json() as Promise<T>
}

function post(body: object, headers?: Record<string, string>): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  }
}

export const api = {
  catalog: () => request<Catalog>('/catalog'),
  submissions: () => request<Submission[]>('/submissions'),
  submit: (body: Schema['CreateSubmission']) => request<Submission>('/submissions', post(body)),
  start: (body: Schema['CreateRun'], key: string) =>
    request<Run>('/runs', post(body, { 'Idempotency-Key': key })),
  run: (id: string) => request<Run>(`/runs/${id}`),
  result: (id: string) => request<Result>(`/runs/${id}/result`),
}
