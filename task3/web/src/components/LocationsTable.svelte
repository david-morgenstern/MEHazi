<script>
  import { get, round, percent } from '../lib/api.js'

  let { onerror } = $props()

  let rows = $state([])
  let location = $state('')

  $effect(() => {
    get('/locations')
      .then((result) => (rows = result))
      .catch(onerror)
  })

  // 36 rows, already in memory: filtering these in the browser costs nothing
  // and a round trip would only make it slower.
  const locations = $derived([...new Set(rows.map((row) => row.location))].sort())
  const shown = $derived(location ? rows.filter((row) => row.location === location) : rows)
</script>

<section class="panel">
  <div class="toolbar">
    <h2>Every location</h2>
    <label>
      Location
      <select bind:value={location}>
        <option value="">all</option>
        {#each locations as name}<option value={name}>{name}</option>{/each}
      </select>
    </label>
  </div>

  <div class="scroll">
    <table>
      <thead>
        <tr>
          <th scope="col">Location</th>
          <th scope="col">Parameter</th>
          <th scope="col" class="num">Readings</th>
          <th scope="col" class="num">Sensors</th>
          <th scope="col" class="num">Mean</th>
          <th scope="col" class="num">σ</th>
          <th scope="col" class="num">Median</th>
          <th scope="col" class="num">p95</th>
          <th scope="col" class="num">Min</th>
          <th scope="col" class="num">Max</th>
          <th scope="col" class="num">Bad</th>
        </tr>
      </thead>
      <tbody>
        {#each shown as row (row.location + row.parameter)}
          <tr>
            <td>{row.location}</td>
            <td>{row.parameter}</td>
            <td class="num">{row.readings.toLocaleString()}</td>
            <td class="num">{row.sensors.toLocaleString()}</td>
            <td class="num">{round(row.avg_value)}</td>
            <td class="num">{round(row.stddev_value)}</td>
            <td class="num">{round(row.median_value)}</td>
            <td class="num">{round(row.p95_value)}</td>
            <td class="num">{round(row.min_value, 2)}</td>
            <td class="num">{round(row.max_value, 2)}</td>
            <td class="num">{percent(row.bad_pct)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <p class="muted">
    Straight from task2's <code>location_stats</code> table, sensor counts included — those are
    approximate, from a HyperLogLog sketch.
  </p>
</section>

<style>
  section {
    margin-top: 1.5rem;
  }

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

  p {
    margin-top: 0.75rem;
    font-size: 0.8rem;
  }
</style>
