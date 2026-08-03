import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";

export function ObservationMap({
  geojson,
  selectedId,
  onSelect,
}: {
  geojson: { features?: Array<Record<string, unknown>> };
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  return (
    <section aria-label="Observation map">
      <AgricultureGeoJsonPreview
        geojson={geojson}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    </section>
  );
}
