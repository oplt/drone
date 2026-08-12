# FE-001 map bundle budgets

The application shell must not preload Google Maps or Cesium. Map routes load
`MapProviders` dynamically, and Cesium is reachable only through
`CesiumMapLazy`.

`frontend/scripts/check_bundle_budgets.mjs` inspects the production
`dist/index.html` module preloads and fails when a preload filename contains:

- `vendor-google-maps`
- `vendor-cesium`
- `cesium`

Run it after a Vite build:

```sh
cd frontend
npm run build
npm run check:bundle-budgets
```

This is a dependency-boundary budget rather than a byte budget: non-map routes
pay zero eager Google Maps/Cesium JavaScript from the application shell.
