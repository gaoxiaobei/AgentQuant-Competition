import type { components } from './api.generated'

type Schema = components['schemas']
export type Catalog = Schema['Catalog']
export type Submission = Schema['Submission']
export type Run = Schema['Run']
export type Result = Schema['EvaluationResult']

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    const message = typeof error?.message === 'string' ? error.message : (
      response.status === 422 ? '请检查输入字段' : `请求失败（${response.status}），请重试`
    )
    throw new ApiError(response.status, message)
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
  catalog: (signal: AbortSignal) => request<Catalog>('/catalog', { signal }),
  submissions: (signal: AbortSignal) => request<Submission[]>('/submissions', { signal }),
  submit: (body: Schema['CreateSubmission']) => request<Submission>('/submissions', post(body)),
  start: (body: Schema['CreateRun'], key: string) =>
    request<Run>('/runs', post(body, { 'Idempotency-Key': key })),
  run: (id: string, signal: AbortSignal) => request<Run>(`/runs/${encodeURIComponent(id)}`, { signal }),
  result: (id: string, signal: AbortSignal) => request<Result>(`/runs/${encodeURIComponent(id)}/result`, { signal }),
}
