import { queryOptions } from '@tanstack/react-query'
import { api } from './api'
import type { Run } from './api'

export const catalogQuery = queryOptions({
  queryKey: ['catalog'],
  queryFn: ({ signal }) => api.catalog(signal),
  staleTime: 60_000,
})

export const submissionsQuery = queryOptions({
  queryKey: ['submissions'],
  queryFn: ({ signal }) => api.submissions(signal),
})

export function runQuery(id: string) {
  return queryOptions({
    queryKey: ['runs', id],
    queryFn: ({ signal }) => api.run(id, signal),
  })
}

export function isPending(run?: Run) {
  return run?.status === 'QUEUED' || run?.status === 'RUNNING'
}
