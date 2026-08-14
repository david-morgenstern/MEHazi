# MEHazi — task 3

A REST API over the sensor data task2 loaded, and a web page that reads it.
One container: FastAPI serves both the endpoints and the compiled front end.

```
   browser ──▶ :8000  ┌──────────────────────────────────────┐
                      │ api    /            the Svelte page  │
                      │        /api/*       five endpoints   │
                      │        /docs        generated schema │
                      └──────────────┬───────────────────────┘
                                     │ task2's network, as db:5432
                                     ▼
                      ┌──────────────────────────────────────┐
                      │ task2's postgres  readings           │
                      │                   location_stats     │
                      └──────────────────────────────────────┘
```

The database is task2's and stays task2's: this stack owns no volume, creates no
schema, and joins task2's compose network rather than reaching in through a
published port. Nothing here duplicates a credential except by default value.

## Run

task2 must be up and loaded first — this is a reader, it has nothing of its own:

```bash
cd task2 && docker compose up -d       # if it is not already running
cd ../task3 && docker compose up -d --build
```

Then open **<http://localhost:8000>**, or **<http://localhost:8000/docs>** for
the API's own documentation, which is generated from the pydantic models and can
issue requests itself. The page itself runs offline; `/docs` is the one thing
here that does not, because FastAPI loads Swagger UI from a CDN.

Behind a corporate proxy, the build needs a route to it — npm and pip are the
only things that reach the internet:

```bash
# -i.bak, then remove it: the one spelling that works on GNU and BSD sed alike.
sed -i.bak 's|^PROXY=.*|PROXY=http://host.docker.internal:3128|' .env && rm -f .env.bak
```

Colleagues on the same network use your hostname: `http://<your-hostname>:8000`.

## The API

Five endpoints. Each returns JSON described by a pydantic model, so the schema
at `/docs` is generated from the same code that produces the responses.

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | whether the database is visible, and how much is in it — `"empty"` rather than `"ok"` when the tables are there but task2 has not filled them |
| `GET /api/sensors?q=&limit=` | sensor ids, optionally narrowed by a fragment |
| `GET /api/sensors/{id}` | one sensor summarised: location, span, bad rate, and per-parameter mean, σ, min and max |
| `GET /api/sensors/{id}/readings?…` | that sensor's processed readings — filtered, sorted, paged |
| `GET /api/locations` | task2's `location_stats`, one row per location and parameter |

```bash
curl -s localhost:8000/api/sensors/003v9hy | head -c 300
curl -s 'localhost:8000/api/sensors/003v9hy/readings?parameter=Offset&sort=value&order=desc&limit=3'
```

### The sensor list is a skip scan

Five thousand sensors live in a million rows, and `SELECT DISTINCT sensor_id`
reads all million to return five thousand — a parallel sequential scan of the
whole table, on every keystroke. Postgres has no skip scan of its own, so
`routes.py` asks for one with a recursive CTE that walks the primary key from
each distinct value to the next: five thousand index lookups instead of a
million row reads. Same index, same answer, and the work no longer grows with
the number of readings — only with the number of sensors.

The wall-clock gap on a million warm rows is smaller than that makes it sound
(tens of milliseconds either way). It is the scaling that earns the CTE, not
the stopwatch.

### Validation, and why the sort parameter is an enum

Pydantic checks everything on the way in. A sensor id must match
`^[0-9a-z]{7}$`, `limit` is bounded (1–500 a page of readings, 1–5000 the sensor
list), `parameter` must be one of the six, and an unrecognised query parameter
is an error rather than silence — `?srot=value` is a typo worth hearing about.

`sort` is a special case. A column name cannot be bound as a parameter the way a
value can, so it has to be interpolated into the SQL — which is only safe
because `SortField` is an enum of eight column names and pydantic rejects
anything else before the request reaches the query:

```console
$ curl -s 'localhost:8000/api/sensors/003v9hy/readings?sort=value;DROP+TABLE+readings'
{"detail":"sort: Input should be 'reading_date', 'parameter', 'value', …"}   # 422
```

### Errors

Every failure leaves as the same object — `{"detail": "one sentence"}` — so the
page can show what went wrong without knowing which kind of failure it was.

| | |
| --- | --- |
| `404` | a well-formed sensor id that has no readings |
| `422` | anything pydantic rejected, flattened to one readable line |
| `503` | the database is unreachable, or its tables do not exist yet |
| `500` | a bug: logged in full, reported without the internals |

The 503 is worth its own note. The pool opens without waiting for a first
connection, so the API starts even when Postgres does not answer yet, says 503
while that is true, and starts serving the moment the database appears — no
restart, no crash loop:

```console
$ docker compose -f ../task2/compose.yaml stop db
$ curl -s localhost:8000/api/health
{"detail":"The sensor database is not reachable. Is task2's stack up and loaded?"}
```

## The page

- a **sensor picker** that filters five thousand ids as you type, debounced to
  one request per pause rather than one per keystroke
- a **summary** of the selected sensor: location, span, bad rate, and a row per
  parameter with its mean, σ and range
- a **readings table** that is sorted and filtered **by the database**, not the
  browser: clicking a header, choosing a parameter or a status, and paging all
  turn into query parameters, so the table behaves the same whether a sensor has
  two hundred rows or two million
- the **location table**, straight from task2's aggregate

The selected sensor lives in the URL — <http://localhost:8000/#003v9hy> — so a
view can be linked to, bookmarked, and survives a reload. Light and dark both
follow the system setting.

### Why Svelte rather than hand-written JavaScript

The brief asks for an HTML page using CSS and JavaScript. **That is exactly what
the browser receives here.** Svelte is a *compiler*, not a runtime library: it
turns the files in `web/src/` into plain HTML, CSS and DOM calls at build time.
Nothing framework-shaped is downloaded — no React, no Vue, no virtual DOM. The
whole page is 54 kB of JavaScript, 20 kB over the wire. The difference from
writing it by hand is a build step, not what ends up in the browser.

The reason to accept that build step is **keeping the screen in sync with the
data**. Consider one interaction here: you pick a different sensor. Six things
must now change — the summary cards, the per-parameter table, the readings
table, the sort arrows, the page counter, and the URL — and the filters must
reset, because they were chosen for a different sensor. Written by hand that is
a function that remembers to touch six places, and the next feature makes it
seven. Missing one is the classic dashboard bug: a stale row under a fresh
heading.

Svelte inverts that. You declare *what the page looks like for a given state*,
change the state, and the page follows. That is why this front end is **smaller**
than the hand-written equivalent, not bigger, despite doing sorting, filtering,
paging, debounced search, error handling and URL state.

Two smaller wins: styles are scoped to their component, so a `table` rule in one
file cannot reach into another; and each feature is one file that reads
top-to-bottom as script → markup → styles.

The cost is honest and contained: a `node` stage in the Dockerfile. Nobody needs
node installed to build or run this — the container does it.

### Reading it without knowing JavaScript

Almost everything in `web/src/` is one of five ideas:

| You see | It means |
| --- | --- |
| `let x = $state(0)` | a variable **the page is watching**. Assign to it and anything showing it redraws |
| `$derived(...)` | a value **computed from** other state; it recalculates itself, you never call it |
| `$effect(() => {...})` | **do this when the state it reads changes.** Every data fetch on the page is one of these |
| `$props()` | the values a **parent passed in**, e.g. which sensor this component should show |
| `{#if ...}` / `{#each ...}` | markup that appears **conditionally**, or **repeats** once per row |

So `components/SensorSummary.svelte` reads, in full:

```svelte
let { sensorId } = $props()      // the parent says which sensor
let summary = $state(null)       // what we know about it — nothing, yet

$effect(() => {                  // when sensorId changes, fetch it again
  get(`/sensors/${sensorId}`).then((result) => (summary = result))
})

{#if !summary}Loading…{:else} …the cards and the table… {/if}
```

That is the whole pattern; the other three components are the same shape with
more markup. `lib/api.js` is the only file that talks to the network, and it is
40 lines of `fetch`.

## Developing

The API reloads on a save, against task2's database through its published port:

```bash
pip install -r requirements.txt
PGHOST=localhost PGPORT=5433 uvicorn app.main:app --reload
```

The front end wants its own dev server, which proxies `/api` to that:

```bash
cd web && npm install && npm run dev
```

Nobody needs node to *build* it — that happens in the image.

## Layout

```
compose.yaml              one service, joined to task2's network
Dockerfile                node builds the page, pip builds a venv, neither ships
.dockerignore             keeps a local node_modules out of the image
requirements.txt          pinned
.env.example              every setting, documented

app/
  main.py                 the app, the pool's lifespan, the error handlers
  config.py               settings, under libpq's own variable names
  db.py                   the pool, and the query helpers that turn a dead
                          database into a 503
  models.py               every request and response, as pydantic models
  routes.py               the five endpoints and their SQL

web/
  package.json            svelte + vite, pinned in package-lock.json
  vite.config.js          build to dist/, proxy /api when developing
  src/
    App.svelte            layout, selection, the error banner
    lib/api.js            fetch, and unwrapping {"detail": …}
    components/           picker, summary, readings table, locations table
    app.css               tokens and the shared table and control styles
```

## Stopping

```bash
docker compose down
```

Nothing to lose: the data is task2's.
