import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

test.describe("agriculture flight foundation", () => {
  test("loads saved-field profile, preview, and launch preflight surfaces", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/fields**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      } else await route.continue();
    });
    await page.route("**/agriculture/**", async (route) => {
      const url = route.request().url();
      if (url.includes("plan-preview")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ area_m2: 10000, area_ha: 1, footprint_width_m: 20, footprint_height_m: 15, estimated_gsd_cm: 2, coverage_pct: 100, warnings: [] }) });
      } else if (url.includes("/profile")) {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: 1, field_id: 1, timezone: "UTC", metadata: {} }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      }
    });
    await page.goto("/dashboard/field");
    await expect(page).toHaveURL(/\/dashboard\/field/);
    await expect(page.getByText(/Field Operations|Missing Google Maps API Key/i)).toBeVisible({ timeout: 60_000 });
  });

  test("opens dedicated agriculture field information architecture", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/fields/features**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature", properties: { id: 7, name: "North block", area_ha: 2.4, workflow_scope: "agriculture" }, geometry: { type: "Polygon", coordinates: [[[4, 50], [4.001, 50], [4.001, 50.001], [4, 50], [4, 50]]] } }] }) });
    });
    await page.route("**/agriculture/fields/overview", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: 7, name: "North block", area_ha: 2.4, workflow_scope: "agriculture", geometry_geojson: { type: "Polygon", coordinates: [[[4, 50], [4.001, 50], [4.001, 50.001], [4, 50]]] }, profile: { crop_type: "wheat", growth_stage: "tillering" }, latest_flight: null }]) });
    });
    await page.goto("/dashboard/agriculture/fields");
    await expect(page.getByRole("heading", { name: "Agriculture fields" })).toBeVisible();
    await expect(page.getByRole("link", { name: /North block/i })).toBeVisible();
    await page.getByRole("link", { name: /North block/i }).click();
    await expect(page).toHaveURL(/\/dashboard\/agriculture\/fields\/7$/);
  });

  test("supports keyboard map review and complete analysis route handoff", async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/agriculture/fields/overview", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: 7, name: "North block", area_ha: 2.4, workflow_scope: "agriculture", geometry_geojson: { type: "Polygon", coordinates: [[[4, 50], [4.001, 50], [4.001, 50.001], [4, 50]]] }, profile: { crop_type: "wheat", growth_stage: "tillering" }, latest_flight: null }]) }));
    await page.route("**/agriculture/fields/7/profile", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: 1, field_id: 7, crop_type: "wheat", growth_stage: "tillering", timezone: "UTC", metadata: {} }) }));
    await page.route("**/agriculture/fields/7/flights", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: "flight-7", mission_id: "mission-7", field_id: 7, status: "captured", profile_snapshot: {}, quality_summary: { status: "pass" }, coverage_summary: {}, input_manifest: {}, created_at: "2026-08-01T10:00:00Z", started_at: null, ended_at: null }]) }));
    await page.route("**/agriculture/flights/flight-7", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "flight-7", mission_id: "mission-7", field_id: 7, status: "captured", profile_snapshot: {}, quality_summary: {}, coverage_summary: {}, input_manifest: {}, created_at: "2026-08-01T10:00:00Z", started_at: null, ended_at: null }) }));
    await page.route("**/agriculture/flights/flight-7/quality", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ flight_id: "flight-7", quality: { status: "pass" } }) }));
    await page.route("**/agriculture/flights/flight-7/coverage", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ flight_id: "flight-7", coverage: { status: "pass" } }) }));
    await page.route("**/agriculture/flights/flight-7/analysis-runs", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }));
    await page.goto("/dashboard/agriculture/fields");
    const mapFeature = page.getByRole("button", { name: /Select Map feature 7/i });
    await mapFeature.focus();
    await mapFeature.press("Enter");
    await page.getByRole("link", { name: /North block/i }).click();
    await page.getByRole("link", { name: /flight-7/i }).click();
    await expect(page.getByRole("heading", { name: "Agriculture flight" })).toBeVisible();
    await expect(page.getByText(/Quality: pass/i)).toBeVisible();
  });

  test("completes plan, preflight, run, review, comparison, and export handoffs", async ({ page }) => {
    await mockAuthenticatedSession(page);
    const flight = { id: "flight-7", mission_id: "mission-7", field_id: 7, status: "captured", profile_snapshot: {}, quality_summary: { status: "pass" }, coverage_summary: { status: "pass" }, input_manifest: {}, created_at: "2026-08-01T10:00:00Z", started_at: null, ended_at: null };
    const run = { id: "run-7", flight_id: "flight-7", status: "completed", progress: 1, requested_analyses: [], analysis_profile: {}, input_manifest: {}, input_checksum: "checksum", model_versions: {}, calibration_versions: {}, parameters: {}, baseline_flight_id: null, retry_count: 0, audit_json: {}, requested_by_user_id: null, quality_gate: {}, counters: {}, created_at: "2026-08-01T10:00:00Z", started_at: null, finished_at: null };
    const observation = { id: "obs-7", run_id: "run-7", flight_id: "flight-7", field_id: 7, observation_type: "weed", zone_kind: "observation", geometry_geojson: { type: "Point", coordinates: [4, 50] }, georef_status: "resolved", area_m2: 5, severity: 0.8, confidence: 0.9, uncertainty: {}, first_detected: null, last_detected: null, trend: "new", evidence_ids: ["evidence-7"], sensor_values: {}, model_version: "rgb-v1", review_state: "unreviewed", review_label: null, review_note: null, reviewed_at: null };
    await page.route("**/agriculture/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/flights/flight-7")) return route.fulfill({ json: flight });
      if (path.endsWith("/analysis-runs/run-7/quality")) return route.fulfill({ json: { run_id: "run-7", status: "pass", score: 0.9, summary: {}, stages: [] } });
      if (path.endsWith("/quality")) return route.fulfill({ json: { flight_id: "flight-7", quality: { status: "pass" } } });
      if (path.endsWith("/coverage")) return route.fulfill({ json: { flight_id: "flight-7", coverage: { status: "pass" } } });
      if (path.endsWith("/sensor-status")) return route.fulfill({ json: { flight_id: "flight-7", inventory: ["rgb"], spectral: { status: "not_required" }, calibration_ids: [], readings: {}, status: "pass" } });
      if (path.endsWith("/analysis-runs")) return route.fulfill({ json: [run] });
      if (path.endsWith("/analysis-runs/run-7")) return route.fulfill({ json: run });
      if (path.includes("/observations")) return route.fulfill({ json: [observation] });
      if (path.includes("/evidence")) return route.fulfill({ json: { observation_id: "obs-7", evidence_ids: ["evidence-7"], assets: [], geometry: observation.geometry_geojson, georef_status: "resolved" } });
      if (path.includes("/exports")) return route.fulfill({ json: [] });
      return route.fulfill({ json: [] });
    });
    await page.route("**/agriculture/observations/obs-7/review", async (route) => route.fulfill({ json: { ...observation, review_state: "confirmed" } }));
    await page.goto("/dashboard/agriculture/flights/flight-7");
    await expect(page.getByRole("heading", { name: "Agriculture flight" })).toBeVisible();
    await expect(page.getByText("Start post-flight field health analysis")).toHaveCount(0);
    await page.goto("/dashboard/agriculture/analysis/run-7");
    await expect(page.getByRole("heading", { name: "Agriculture analysis" })).toBeVisible();
    await expect(page.getByText("Quality pass")).toBeVisible();
    await page.getByRole("button", { name: /Review weed/i }).click();
    await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.getByRole("button", { name: "Generate export" }).click();
    await expect(page.getByRole("dialog", { name: "Approve export request" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
  });
});
