import { Suspense } from "react";
import Grid from "@mui/material/Grid";
import DashboardPanelSkeleton from "./DashboardPanelSkeleton";
import PageViewsBarChart from "./PageViewsBarChart";
import SessionsChart from "./SessionsChart";
import {
  deltaLabelFromSeries,
  formatNumber,
} from "../utils/dashboardFormatters";

type DashboardTrendChartsProps = {
  labels: string[];
  flightHours?: number[];
  flightCounts?: number[];
  telemetryCounts?: number[];
  surveyHours7d?: number;
  flights24h?: number;
};

export default function DashboardTrendCharts({
  labels,
  flightHours = [],
  flightCounts = [],
  telemetryCounts = [],
  surveyHours7d,
  flights24h,
}: DashboardTrendChartsProps) {
  const last7Labels = labels.slice(-7);
  const last7Flights = flightCounts.slice(-7);
  const last7Telemetry = telemetryCounts.slice(-7);
  const hasTrendData = flightHours.length > 0;
  const hasWorkloadData = last7Flights.length > 0 || last7Telemetry.length > 0;

  return (
    <Grid container spacing={2} columns={12}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Suspense fallback={<DashboardPanelSkeleton height={360} />}>
          <SessionsChart
            title="Survey hours"
            totalValue={formatNumber(surveyHours7d, "h")}
            deltaLabel={deltaLabelFromSeries(flightHours)}
            subtitle="Survey hours per day for the last 30 days"
            labels={hasTrendData ? labels : undefined}
            series={
              hasTrendData
                ? [{ id: "hours", label: "Hours", data: flightHours }]
                : undefined
            }
          />
        </Suspense>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Suspense fallback={<DashboardPanelSkeleton height={360} />}>
          <PageViewsBarChart
            title="Workload mix"
            totalValue={formatNumber(flights24h)}
            deltaLabel={deltaLabelFromSeries(flightCounts)}
            subtitle="Flights and telemetry points for the last 7 days"
            labels={hasWorkloadData ? last7Labels : undefined}
            series={
              hasWorkloadData
                ? [
                    { id: "flights", label: "Flights", data: last7Flights },
                    {
                      id: "telemetry",
                      label: "Telemetry",
                      data: last7Telemetry,
                    },
                  ]
                : undefined
            }
          />
        </Suspense>
      </Grid>
    </Grid>
  );
}
