<script>
  import { get, round, percent } from '../lib/api.js'

  let { sensorId, onerror } = $props()

  let summary = $state(null)

  $effect(() => {
    const id = sensorId
    summary = null
    get(`/sensors/${id}`)
      .then((result) => (summary = result))
      .catch(onerror)
  })
</script>

<section class="panel">
  <h2>{sensorId}</h2>

  {#if !summary}
    <p class="muted">Loading…</p>
  {:else}
    <div class="cards">
      <div class="card">
        <span>Location</span>
        <strong>{summary.location}</strong>
      </div>
      <div class="card">
        <span>Readings</span>
        <strong>{summary.readings.toLocaleString()}</strong>
      </div>
      <div class="card">
        <span>Recorded</span>
        <strong>{summary.first_reading} → {summary.last_reading}</strong>
      </div>
      <div class="card" class:warn={summary.bad_readings > 0}>
        <span>Bad</span>
        <strong>{summary.bad_readings} · {percent(summary.bad_pct)}</strong>
      </div>
    </div>

    <table>
      <caption>Per parameter</caption>
      <thead>
        <tr>
          <th scope="col">Parameter</th>
          <th scope="col" class="num">Readings</th>
          <th scope="col" class="num">Mean</th>
          <th scope="col" class="num">σ</th>
          <th scope="col" class="num">Min</th>
          <th scope="col" class="num">Max</th>
          <th scope="col" class="num">Bad</th>
        </tr>
      </thead>
      <tbody>
        {#each summary.parameters as row (row.parameter)}
          <tr>
            <td>{row.parameter}</td>
            <td class="num">{row.readings}</td>
            <td class="num">{round(row.avg_value)}</td>
            <td class="num">{round(row.stddev_value)}</td>
            <td class="num">{round(row.min_value)}</td>
            <td class="num">{round(row.max_value)}</td>
            <td class="num">{percent(row.bad_pct)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  h2 {
    font-family: var(--mono);
    font-size: 1.1rem;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: 0.75rem;
    margin: 1rem 0 1.5rem;
  }

  .card {
    display: grid;
    gap: 0.25rem;
    padding: 0.75rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg);
  }

  .card span {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }

  .card strong {
    font-size: 0.95rem;
    font-variant-numeric: tabular-nums;
  }

  .card.warn strong {
    color: var(--bad-text);
  }
</style>
