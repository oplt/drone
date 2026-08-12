import type { Page, Route } from "@playwright/test";

const now = "2026-08-01T10:00:00Z";

function projectFixture() {
  return {
    id: "project-1",
    name: "Tomato field detector",
    description: "E2E fixture",
    crop: "tomato",
    task_type: "detection",
    status: "active",
    classes: [
      { id: "class-ripe", name: "ripe_tomato", class_index: 0 },
      { id: "class-damaged", name: "damaged_tomato", class_index: 1 },
    ],
    dataset_count: 0,
    latest_dataset_status: null,
    latest_model_version: null,
    production_model_version: null,
    created_at: now,
    updated_at: now,
  };
}

function datasetFixture() {
  return {
    id: "dataset-1",
    project_id: "project-1",
    version: 1,
    status: "draft",
    source_count: 0,
    image_count: 0,
    selected_count: 0,
    labeled_count: 0,
    reviewed_count: 0,
    train_count: 0,
    val_count: 0,
    test_count: 0,
    manifest_checksum: "dataset-checksum",
    locked_at: null,
    created_at: now,
    updated_at: now,
  };
}

function imageFixture(index: number) {
  return {
    id: `image-${index}`,
    dataset_id: "dataset-1",
    content_url: `/vision/images/image-${index}/content`,
    thumbnail_url: `/vision/images/image-${index}/thumbnail`,
    source_type: "upload",
    source_video_id: null,
    mission_id: null,
    field_id: null,
    frame_index: null,
    timestamp_seconds: null,
    width: 1000,
    height: 600,
    quality_score: 0.94,
    selected: true,
    split: index === 1 ? "train" : index === 2 ? "val" : "test",
    annotation_status: "unlabeled",
    annotations: [],
    lat: null,
    lon: null,
    altitude_m: null,
    heading_deg: null,
    metadata: { original_filename: `tomato-${index}.jpg` },
    created_at: now,
  };
}

export type VisionMockState = ReturnType<typeof createVisionMockState>;

export function createVisionMockState(preloaded = false) {
  const project = projectFixture();
  const dataset = datasetFixture();
  const images = preloaded ? [imageFixture(1), imageFixture(2)] : [];
  if (preloaded) {
    project.dataset_count = 1;
    project.latest_dataset_status = "draft";
    Object.assign(dataset, {
      source_count: 1,
      image_count: 2,
      selected_count: 2,
      train_count: 1,
      val_count: 1,
    });
  }
  return {
    projects: preloaded ? [project] : [] as typeof project[],
    project,
    dataset: preloaded ? dataset : null as typeof dataset | null,
    images,
    models: [] as Record<string, unknown>[],
    trainingRuns: [] as Record<string, unknown>[],
    annotationRequests: [] as Array<{
      imageId: string;
      annotations: Array<Record<string, unknown>>;
      reviewed: boolean;
    }>,
    lastVideoPayload: null as Record<string, unknown> | null,
  };
}

function refreshDataset(state: VisionMockState) {
  const dataset = state.dataset;
  if (!dataset) return;
  dataset.image_count = state.images.length;
  dataset.selected_count = state.images.filter((image) => image.selected).length;
  dataset.labeled_count = state.images.filter(
    (image) => image.annotation_status !== "unlabeled",
  ).length;
  dataset.reviewed_count = state.images.filter(
    (image) => image.annotation_status === "reviewed",
  ).length;
}

function evaluationFixture() {
  return {
    model_version_id: "version-1",
    model_name: "Tomato field detector",
    version: 1,
    state: "completed",
    metrics: {},
    summary: {
      precision: 0.928,
      recall: 0.871,
      f1: 0.898,
      map50: 0.913,
      map75: 0.781,
      map50_95: 0.683,
    },
    per_class: [{
      class_index: 0,
      class_name: "ripe_tomato",
      precision: 0.95,
      recall: 0.9,
      f1: 0.924,
      map50: 0.94,
      map75: 0.8,
      map50_95: 0.72,
    }],
    confusion_matrix: [[8, 1], [2, 7]],
    confusion_matrix_labels: ["ripe_tomato", "background"],
    dataset_id: "dataset-1",
    dataset_version: 1,
    dataset_image_count: 3,
    test_image_count: 1,
    dataset_checksum: "dataset-checksum",
    split: "test",
    image_size: 640,
    base_model: "yolo26s.pt",
    preset: "balanced",
    training_date: now,
    evaluated_at: now,
    artifacts: [],
  };
}

async function visionRoute(route: Route, state: VisionMockState) {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const method = request.method();
  if (path.endsWith("/vision/projects") && method === "GET")
    return route.fulfill({ json: state.projects });
  if (path.endsWith("/vision/projects") && method === "POST") {
    const payload = request.postDataJSON();
    state.project.name = payload.name;
    state.project.crop = payload.crop;
    state.project.classes = payload.classes.map(
      (item: { name: string }, index: number) => ({
        id: index ? "class-damaged" : "class-ripe",
        name: item.name.replaceAll(" ", "_"),
        class_index: index,
      }),
    );
    state.projects = [state.project];
    return route.fulfill({ json: state.project });
  }
  if (path.endsWith("/vision/models") && method === "GET")
    return route.fulfill({ json: state.models });
  if (/\/vision\/projects\/[^/]+\/datasets$/.test(path) && method === "GET")
    return route.fulfill({ json: state.dataset ? [state.dataset] : [] });
  if (/\/vision\/projects\/[^/]+\/datasets$/.test(path) && method === "POST") {
    state.dataset = datasetFixture();
    state.project.dataset_count = 1;
    state.project.latest_dataset_status = "draft";
    return route.fulfill({ json: state.dataset });
  }
  if (path.endsWith("/vision/datasets/dataset-1") && method === "GET")
    return route.fulfill({ json: state.dataset });
  if (path.endsWith("/vision/datasets/dataset-1/images") && method === "POST") {
    state.images = [imageFixture(1), imageFixture(2), imageFixture(3)];
    state.images[1].annotation_status = "reviewed";
    state.images[2].annotation_status = "reviewed";
    if (state.dataset) {
      state.dataset.source_count = 1;
      state.dataset.train_count = 1;
      state.dataset.val_count = 1;
      state.dataset.test_count = 1;
    }
    refreshDataset(state);
    return route.fulfill({
      json: { added: 3, duplicates: 0, rejected: [], images: state.images },
    });
  }
  if (path.endsWith("/vision/datasets/dataset-1/images") && method === "GET")
    return route.fulfill({
      json: { items: state.images, total: state.images.length, offset: 0, limit: 200 },
    });
  const annotationMatch = path.match(/\/vision\/images\/(image-\d+)\/annotations$/);
  if (annotationMatch && method === "PUT") {
    const payload = request.postDataJSON();
    const image = state.images.find((item) => item.id === annotationMatch[1]);
    if (!image) return route.fulfill({ status: 404, json: { detail: "missing" } });
    image.annotations = payload.annotations.map(
      (annotation: Record<string, unknown>, index: number) => ({
        id: annotation.id ?? `${image.id}-annotation-${index + 1}`,
        annotation_type: "bbox",
        source: "manual",
        confidence: null,
        created_at: now,
        updated_at: now,
        ...annotation,
      }),
    );
    image.annotation_status = payload.reviewed
      ? "reviewed"
      : image.annotations.length ? "labeled" : "unlabeled";
    state.annotationRequests.push({
      imageId: image.id,
      annotations: payload.annotations,
      reviewed: payload.reviewed,
    });
    refreshDataset(state);
    return route.fulfill({ json: image });
  }
  if (/\/vision\/images\/image-\d+\/(content|thumbnail)$/.test(path))
    return route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#476f3c"/><circle cx="500" cy="300" r="110" fill="#d84937"/></svg>',
    });
  if (path.endsWith("/vision/projects/project-1/training-runs") && method === "GET")
    return route.fulfill({ json: state.trainingRuns });
  if (path.endsWith("/vision/projects/project-1/training-runs") && method === "POST") {
    const model = {
      id: "version-1",
      model_id: "model-1",
      project_id: "project-1",
      training_run_id: "run-1",
      dataset_id: "dataset-1",
      name: state.project.name,
      crop: state.project.crop,
      task_type: "detection",
      version: 1,
      architecture: "yolo26s.pt",
      status: "candidate",
      classes: state.project.classes.map((item) => item.name),
      metrics: evaluationFixture().metrics,
      created_at: now,
    };
    const run = {
      id: "run-1", project_id: "project-1", dataset_id: "dataset-1",
      status: "completed", trainer: "ultralytics", base_model: "yolo26s.pt",
      preset: "balanced", epochs: 50, total_epochs: 50, image_size: 640,
      batch_size: 8, device: "cpu", progress: 100, current_epoch: 50,
      metrics: evaluationFixture().metrics, error: null, model_version_id: "version-1",
      started_at: now, finished_at: now, created_at: now,
    };
    state.models = [model];
    state.trainingRuns = [run];
    return route.fulfill({ json: run });
  }
  if (path.endsWith("/vision/model-versions/version-1/evaluation"))
    return route.fulfill({ json: evaluationFixture() });
  if (path.endsWith("/vision/model-versions/version-1/deploy") && method === "POST") {
    state.models[0].status = "production";
    state.project.production_model_version = 1;
    return route.fulfill({ json: state.models[0] });
  }
  return route.fulfill({ status: 404, json: { detail: `Unhandled ${method} ${path}` } });
}

async function videoRoute(route: Route, state: VisionMockState) {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const method = request.method();
  const video = {
    id: "video-1", mission_id: null, field_id: null,
    original_filename: "tomato-flight.mp4", fps: 30, width: 1920, height: 1080,
    duration_seconds: 3, status: "uploaded", created_at: now,
  };
  const job = {
    id: "job-1", video_id: video.id, mission_id: null, status: "completed",
    progress: 100, error: null, model_name: state.project.name,
    model_version_id: "version-1", model_version: "registered:version-1:checksum",
    small_object_mode: true, tracking_enabled: true, tracker_type: "bytetrack",
    frame_stride_seconds: 1, confidence_threshold: 0.35,
    started_at: now, finished_at: now, created_at: now,
  };
  if (path.endsWith("/video-analysis/videos") && method === "POST")
    return route.fulfill({ json: video });
  if (path.endsWith("/video-analysis/videos") && method === "GET")
    return route.fulfill({ json: [] });
  if (path.endsWith("/video-analysis/videos/video-1/analyze") && method === "POST") {
    state.lastVideoPayload = request.postDataJSON();
    return route.fulfill({ json: job });
  }
  if (path.endsWith("/video-analysis/jobs/job-1")) return route.fulfill({ json: job });
  if (path.includes("/video-analysis/jobs/job-1/detections"))
    return route.fulfill({ json: [{
      id: "detection-1", job_id: "job-1", video_id: "video-1", frame_index: 1,
      timestamp_seconds: 1, label: "ripe_tomato", confidence: 0.91,
      x1: 100, y1: 100, x2: 180, y2: 180, track_id: 1,
    }] });
  if (path.endsWith("/video-analysis/jobs/job-1/summary"))
    return route.fulfill({ json: {
      job_id: "job-1", frames_analyzed: 3, detections_by_class: { ripe_tomato: 3 },
      unique_tracked_objects_by_class: { ripe_tomato: 1 },
      confidence_distribution: { minimum: 0.8, mean: 0.9, maximum: 0.95 },
      model_name: state.project.name, model_version: "registered:version-1:checksum",
      model_version_id: "version-1",
      registered_model: { name: state.project.name, version: 1, crop: "tomato", task_type: "detection", classes: ["ripe_tomato"] },
      tracking_enabled: true, tracker_type: "bytetrack", small_object_mode: true,
      frame_stride_seconds: 1, confidence_threshold: 0.35,
    } });
  if (path.endsWith("/stream")) return route.fulfill({ status: 204, body: "" });
  return route.fulfill({ status: 404, json: { detail: `Unhandled ${method} ${path}` } });
}

export async function mockVisionWorkflow(page: Page, state: VisionMockState) {
  await page.route("**/vision/**", (route) => visionRoute(route, state));
  await page.route("**/video-analysis/**", (route) => videoRoute(route, state));
  await page.route("**/live-object-detection/detections**", (route) =>
    route.fulfill({ json: [] }),
  );
}
