import { useParams } from "react-router-dom";
import MasterScreen from "@/components/MasterScreen";
import SingletonMaster from "@/components/SingletonMaster";
import { MASTERS, SINGLETONS } from "@/config/mastersConfig";
import { EmptyState, PageHeader } from "@/components/ui-kit";

// Single page that renders any master by its route key (/masters/:key).
// List masters use MasterScreen; statutory-detail singletons use SingletonMaster.
export default function MastersPage() {
  const { key } = useParams();
  const listConfig = MASTERS[key];
  const singletonConfig = SINGLETONS[key];

  if (listConfig) return <MasterScreen key={key} config={listConfig} />;
  if (singletonConfig) return <SingletonMaster key={key} config={singletonConfig} />;

  return (
    <div>
      <PageHeader eyebrow="Masters" title="Unknown master" description={`No master configured for "${key}".`} />
      <EmptyState message="Pick a master from the sidebar" />
    </div>
  );
}
