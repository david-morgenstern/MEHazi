<script>
  import { get } from './lib/api.js'
  import SensorPicker from './components/SensorPicker.svelte'
  import SensorSummary from './components/SensorSummary.svelte'
  import ReadingsTable from './components/ReadingsTable.svelte'
  import LocationsTable from './components/LocationsTable.svelte'

  // The selected sensor lives in the URL, so a view can be linked to, kept in a
  // bookmark, and survives a reload.
  const fromHash = () => {
    const id = location.hash.slice(1)
    return /^[0-9a-z]{7}$/.test(id) ? id : null
  }

  let sensorId = $state(fromHash())
  let health = $state(null)
  let error = $state(null)

  // Every child reports failures here, so there is one place to look and one
  // banner to dismiss.
  const fail = (problem) => (error = problem.message)

  function select(id) {
    sensorId = id
    location.hash = id
  }

  $effect(() => {
    // Back and forward should move between sensors, not out of the page.
    const follow = () => (sensorId = fromHash())
    addEventListener('hashchange', follow)
    return () => removeEventListener('hashchange', follow)
  })

  $effect(() => {
    get('/health')
      .then((result) => (health = result))
      .catch(fail)
  })
</script>

<header>
  <div>
    <h1>Sensor explorer</h1>
    <p>Aggregated views of the readings task2 generated, processed and loaded.</p>
  </div>
  {#if health}
    <p class="health">
      <strong>{health.readings.toLocaleString()}</strong> readings ·
      <strong>{health.summaries}</strong> location summaries
    </p>
  {/if}
</header>

{#if error}
  <div class="banner" role="alert">
    <span>{error}</span>
    <button onclick={() => (error = null)} aria-label="Dismiss">×</button>
  </div>
{/if}

<main>
  <aside>
    <SensorPicker selected={sensorId} onselect={select} onerror={fail} />
  </aside>

  <section class="detail">
    {#if sensorId}
      <!-- Keyed so switching sensor remounts both: filters, sort and page all
           reset rather than carrying over to a sensor they were not chosen for. -->
      {#key sensorId}
        <SensorSummary {sensorId} onerror={fail} />
        <ReadingsTable {sensorId} onerror={fail} />
      {/key}
    {:else}
      <p class="empty">Pick a sensor on the left to see its readings.</p>
    {/if}
  </section>
</main>

<LocationsTable onerror={fail} />

<style>
  header {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  h1 {
    font-size: 1.5rem;
    letter-spacing: -0.02em;
  }

  header p {
    color: var(--muted);
    font-size: 0.9rem;
  }

  .health strong {
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }

  .banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
    padding: 0.75rem 1rem;
    border: 1px solid var(--bad-border);
    border-radius: var(--radius);
    background: var(--bad-bg);
    color: var(--bad-text);
  }

  .banner button {
    border: 0;
    background: none;
    color: inherit;
    cursor: pointer;
    font-size: 1.25rem;
    line-height: 1;
  }

  main {
    display: grid;
    grid-template-columns: minmax(14rem, 18rem) minmax(0, 1fr);
    gap: 1.5rem;
    align-items: start;
  }

  .detail {
    display: grid;
    gap: 1.5rem;
    min-width: 0;
  }

  .empty {
    padding: 3rem 1rem;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    color: var(--muted);
    text-align: center;
  }

  @media (max-width: 720px) {
    main {
      grid-template-columns: 1fr;
    }
  }
</style>
