<script>
  import { get } from '../lib/api.js'

  let { selected = null, onselect, onerror } = $props()

  const LIMIT = 200

  // Seeded from the selection, so arriving on a link to one sensor shows that
  // sensor in the list rather than the first two hundred of five thousand.
  let fragment = $state(selected ?? '')
  let list = $state({ items: [], total: 0, truncated: false })
  let loading = $state(false)

  // Debounced: typing three characters should cost one request, not three.
  $effect(() => {
    const wanted = fragment
    loading = true
    const timer = setTimeout(async () => {
      try {
        list = await get('/sensors', { q: wanted, limit: LIMIT })
      } catch (problem) {
        onerror(problem)
      } finally {
        loading = false
      }
    }, 200)
    return () => clearTimeout(timer)
  })

  // The API only accepts base-36 fragments, so keep the input to what it will
  // take rather than letting the user type their way into a 422.
  function clean(event) {
    fragment = event.currentTarget.value.toLowerCase().replace(/[^0-9a-z]/g, '').slice(0, 7)
  }
</script>

<div class="picker">
  <label for="sensor-filter">Sensor</label>

  <input
    id="sensor-filter"
    type="search"
    placeholder="filter, e.g. a3"
    value={fragment}
    oninput={clean}
    autocomplete="off"
  />

  <select
    size="12"
    value={selected}
    onchange={(event) => onselect(event.currentTarget.value)}
    aria-label="Sensor ids"
  >
    {#each list.items as id (id)}
      <option value={id}>{id}</option>
    {/each}
  </select>

  <p class="count" class:loading>
    {#if loading}
      searching…
    {:else if list.total === 0}
      no sensor matches
    {:else if list.truncated}
      showing {list.items.length} of {list.total.toLocaleString()} — keep typing
    {:else}
      {list.total.toLocaleString()} {list.total === 1 ? 'sensor' : 'sensors'}
    {/if}
  </p>
</div>

<style>
  .picker {
    display: grid;
    gap: 0.5rem;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
  }

  label {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
  }

  select {
    padding: 0.25rem;
    font-family: var(--mono);
  }

  select option {
    padding: 0.15rem 0.4rem;
  }

  .count {
    font-size: 0.8rem;
    color: var(--muted);
  }

  .count.loading {
    font-style: italic;
  }
</style>
