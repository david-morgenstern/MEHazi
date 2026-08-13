// The one place that talks to the API.
//
// Every error the backend can produce arrives as {"detail": "..."} whatever its
// status code, so unwrapping it here means no component has to think about HTTP.

const BASE = '/api'

export async function get(path, params = {}) {
  const url = new URL(BASE + path, location.origin)
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, value)
    }
  }

  let response
  try {
    response = await fetch(url)
  } catch (cause) {
    // No response at all: the container is down, or the network is.
    throw new Error('The API did not answer.', { cause })
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `${response.status} ${response.statusText}`)
  }
  return response.json()
}

// Numbers arrive as doubles and are shown in tables, where a ragged number of
// decimals is hard to scan.
export function round(value, places = 3) {
  return value === null || value === undefined ? '—' : value.toFixed(places)
}

export function percent(value) {
  return value === null || value === undefined ? '—' : `${value.toFixed(2)}%`
}
