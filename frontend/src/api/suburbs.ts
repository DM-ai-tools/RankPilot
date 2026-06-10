import { apiGet, apiPostJson } from "./client";

export type SuburbGeoItem = {
  suburb_id: string;
  suburb: string;
  lat: number;
  lng: number;
  geojson_polygon: GeoJSON.Polygon | GeoJSON.MultiPolygon;
};

export function fetchSuburbCatalog(metroLabel: string) {
  const params = new URLSearchParams({ metro_label: metroLabel });
  return apiGet<{ metro_label: string; suburbs: string[] }>(`/api/v1/suburbs/catalog?${params}`);
}

export function fetchSuburbGeo(suburbIds: string[]) {
  return apiPostJson<{ items: SuburbGeoItem[] }, { suburb_ids: string[] }>(
    "/api/v1/suburbs/geo",
    { suburb_ids: suburbIds },
  );
}
