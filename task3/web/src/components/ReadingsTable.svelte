<script>
  import { get, round } from '../lib/api.js'

  let { sensorId, onerror } = $props()

  const PARAMETERS = ['Offset', 'Noise', 'Temperature', 'Pressure', 'Humidity', 'Voltage']
  const COLUMNS = [
    { key: 'reading_date', label: 'Date' },
    { key: 'parameter', label: 'Parameter' },
    { key: 'value', label: 'Value', num: true },
    { key: 'delta', label: 'Δ', num: true },
    { key: 'rolling_avg_7d', label: '7d avg', num: true },
    { key: 'z_score', label: 'z', num: true },
    { key: 'reading_no', label: '#', num: true },
    { key: 'status', label: 'Status' },
  ]

  // Mirrors the API's query model; the server does the sorting and filtering,
  // so this is the whole of the table's state.
  let query = $state({
    parameter: '',
    status: '',
    sort: 'reading_date',
    order: 'asc',
    limit: 50,
    offset: 0,
  })

  let page = $state(null)
  let loading = $state(false)

  $effect(() => {
    const request = { ...query }
    loading = true

    // Responses can arrive out of order -- click Next twice and the first
    // request may land last -- so a superseded one is dropped rather than
    // painted over the newer rows. The teardown runs when the effect re-runs,
    // which is exactly when this request stopped being the one we asked for.
    let superseded = false

    get(`/sensors/${sensorId}/readings`, request)
      .then((result) => {
        if (!superseded) page = result
      })
      .catch((problem) => {
        if (!superseded) onerror(problem)
      })
      .finally(() => {
        if (!superseded) loading = false
      })

    return () => (superseded = true)
  })

  function sortBy(column) {
    if (query.sort === column) {
      query.order = query.order === 'asc' ? 'desc' : 'asc'
    } else {
      query.sort = column
      query.order = 'asc'
    }
    query.offset = 0 // a new order makes the old page number meaningless
  }

  function filter(field, value) {
    query[field] = value
    query.offset = 0
  }

  // Counted off the response, not the request: the API echoes back the offset
  // it actually served, so the label describes the rows on screen even while a
  // newer request is still in flight or has just failed.
  const shown = $derived(page ? page.items.length : 0)
  const from = $derived(shown ? page.offset + 1 : 0)
  const to = $derived(page ? page.offset + shown : 0)
  const hasMore = $derived(page ? to < page.total : false)
</script>

<section class="panel">
  <div class="toolbar">
    <h2>Readings</h2>

    <label>
      Parameter
      <select value={query.parameter} onchange={(e) => filter('parameter', e.currentTarget.value)}>
        <option value="">all</option>
        {#each PARAMETERS as name}<option value={name}>{name}</option>{/each}
      </select>
    </label>

    <label>
      Status
      <select value={query.status} onchange={(e) => filter('status', e.currentTarget.value)}>
        <option value="">all</option>
        <option value="Good">Good</option>
        <option value="Bad">Bad</option>
      </select>
    </label>

    <label>
      Rows
      <select value={query.limit} onchange={(e) => filter('limit', Number(e.currentTarget.value))}>
        {#each [25, 50, 100, 200] as size}<option value={size}>{size}</option>{/each}
      </select>
    </label>
  </div>

  <div class="scroll">
    <table class:loading>
      <thead>
        <tr>
          {#each COLUMNS as column}
            <th
              scope="col"
              class:num={column.num}
              class:sorted={query.sort === column.key}
              aria-sort={query.sort === column.key
                ? query.order === 'asc'
                  ? 'ascending'
                  : 'descending'
                : 'none'}
            >
              <button onclick={() => sortBy(column.key)}>
                {column.label}
                <span class="arrow">
                  {query.sort === column.key ? (query.order === 'asc' ? '▲' : '▼') : ''}
                </span>
              </button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each page?.items ?? [] as row (row.parameter + row.reading_no)}
          <tr>
            <td>{row.reading_date}</td>
            <td>{row.parameter}</td>
            <td class="num">{round(row.value)}</td>
            <!-- Null is the first reading of a series, with nothing to compare
                 against; that is what deserves to recede, not a negative. -->
            <td class="num" class:none={row.delta === null}>{round(row.delta)}</td>
            <td class="num">{round(row.rolling_avg_7d)}</td>
            <td
              class="num"
              class:none={row.z_score === null}
              class:outlier={row.z_score !== null && Math.abs(row.z_score) > 2}
            >
              {round(row.z_score, 2)}
            </td>
            <td class="num">{row.reading_no}</td>
            <td><span class="pill {row.status.toLowerCase()}">{row.status}</span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if page && page.total === 0}
    <p class="muted">Nothing matches this filter.</p>
  {/if}

  <div class="pager">
    <button disabled={query.offset === 0} onclick={() => (query.offset -= query.limit)}>
      ← Previous
    </button>
    <span>
      {#if page}{from.toLocaleString()}–{to.toLocaleString()} of {page.total.toLocaleString()}{/if}
    </span>
    <button disabled={!hasMore} onclick={() => (query.offset += query.limit)}>Next →</button>
  </div>
</section>

<style>
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .toolbar h2 {
    margin-right: auto;
    font-size: 1.1rem;
  }

  .toolbar label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    color: var(--muted);
  }

  th button {
    display: flex;
    gap: 0.35rem;
    align-items: center;
    width: 100%;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  th.num button {
    justify-content: flex-end;
  }

  th.sorted {
    color: var(--text);
  }

  .arrow {
    font-size: 0.65em;
    color: var(--accent);
  }

  table.loading {
    opacity: 0.55;
  }

  td.none {
    color: var(--muted);
  }

  td.outlier {
    color: var(--bad-text);
    font-weight: 600;
  }

  .pager {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 1rem;
    font-size: 0.85rem;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
</style>
