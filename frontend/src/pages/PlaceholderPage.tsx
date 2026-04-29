import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";

export function PlaceholderPage({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <>
      <TopBar title={title} subtitle={subtitle} />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">
        <Card>
          <CardHeader title="Coming soon" subtitle="UI shell matches Traffic Radius mockups — wire to API next." />
          <div className="p-5 text-sm text-rp-tmid">
            This section will connect to <code className="rounded bg-rp-light px-1">/api/v1</code> when backends are
            ready.
          </div>
        </Card>
      </div>
    </>
  );
}
